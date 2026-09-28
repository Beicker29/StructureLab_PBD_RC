"""Deterministic DAG planning and sequential V2 workflow execution."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    StageMessage,
    StageResult,
)
from structurelab_pbd_rc.core.exceptions import (
    ContractError,
    DependencyError,
    HandlerRegistrationError,
    WorkflowCycleError,
    WorkflowError,
)
from structurelab_pbd_rc.io.artifacts import PublicationTransaction, TransactionalPublisher
from structurelab_pbd_rc.workflow.catalog import DEFAULT_CATALOG, ModuleCatalog, ModuleDefinition
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.registry import (
    HandlerOutput,
    HandlerRegistry,
    StageExecutionRequest,
    default_handler_registry,
)
from structurelab_pbd_rc.workflow.reuse import (
    PublishedRunIndex,
    ReuseSelection,
    expected_provenance,
    module_content_hash,
    select_reusable_module,
)


class PlanStatus(str, Enum):
    READY = "ready"
    REUSABLE = "reusable"
    INVALIDATED = "invalidated"
    NOT_IMPLEMENTED = "not_implemented"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PlanEntry:
    module_id: str
    stage_number: str
    status: PlanStatus
    reason: str
    required_dependencies: tuple[str, ...]
    reason_code: str = "status"
    reason_details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason_details",
            MappingProxyType(dict(self.reason_details)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "stage_number": self.stage_number,
            "status": self.status.value,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "reason_details": dict(self.reason_details),
            "required_dependencies": list(self.required_dependencies),
        }


@dataclass(frozen=True)
class WorkflowPlan:
    requested_modules: tuple[str, ...]
    execution_order: tuple[str, ...]
    entries: tuple[PlanEntry, ...]
    reuse_selections: Mapping[str, ReuseSelection] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reuse_selections",
            MappingProxyType(dict(self.reuse_selections)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_modules": list(self.requested_modules),
            "execution_order": list(self.execution_order),
            "modules": [entry.to_dict() for entry in self.entries],
        }

    def entry(self, module_id: str) -> PlanEntry:
        for item in self.entries:
            if item.module_id == module_id:
                return item
        raise WorkflowError(f"Module {module_id!r} is not part of this workflow plan.")


@dataclass(frozen=True)
class WorkflowRunResult:
    context: RunContext
    requested_modules: tuple[str, ...]
    execution_order: tuple[str, ...]
    stage_results: tuple[StageResult, ...]
    published_path: str | None

    @property
    def completed(self) -> bool:
        return bool(self.stage_results) and all(result.completed for result in self.stage_results)

    def result(self, module_id: str) -> StageResult:
        for item in self.stage_results:
            if item.module_id == module_id:
                return item
        raise WorkflowError(f"Module {module_id!r} is not part of this workflow run.")


class WorkflowDAG:
    """Validated required-dependency graph derived from a ModuleCatalog."""

    def __init__(self, catalog: ModuleCatalog) -> None:
        self.catalog = catalog
        self._modules = {item.module_id: item for item in catalog.modules}
        self._validate_dependencies()
        self._all_order = self._topological_order(set(self._modules))

    def _validate_dependencies(self) -> None:
        known = set(self._modules)
        for module in self._modules.values():
            for dependency in module.dependencies:
                if dependency not in known:
                    raise DependencyError(
                        f"Module {module.module_id!r} requires unknown dependency "
                        f"{dependency!r}."
                    )

    def required_closure(self, requested_modules: str | Iterable[str]) -> set[str]:
        requested = (
            (requested_modules,)
            if isinstance(requested_modules, str)
            else tuple(requested_modules)
        )
        if not requested:
            raise WorkflowError("At least one semantic module_id must be requested.")
        closure: set[str] = set()
        visiting: set[str] = set()

        def visit(module_id: str) -> None:
            if module_id in visiting:
                cycle = " -> ".join((*sorted(visiting), module_id))
                raise WorkflowCycleError(f"Module dependency cycle detected: {cycle}.")
            if module_id in closure:
                return
            try:
                module = self._modules[module_id]
            except KeyError as exc:
                raise WorkflowError(
                    f"Unknown semantic module_id {module_id!r}; numeric and V1 aliases "
                    "are not accepted."
                ) from exc
            visiting.add(module_id)
            for dependency in module.dependencies:
                visit(dependency)
            visiting.remove(module_id)
            closure.add(module_id)

        for module_id in requested:
            visit(module_id)
        return closure

    def execution_order(self, requested_modules: str | Iterable[str]) -> tuple[str, ...]:
        return self._topological_order(self.required_closure(requested_modules))

    @property
    def all_modules_order(self) -> tuple[str, ...]:
        return self._all_order

    def _topological_order(self, selected: set[str]) -> tuple[str, ...]:
        indegree = {module_id: 0 for module_id in selected}
        dependents: dict[str, set[str]] = {module_id: set() for module_id in selected}
        for module_id in selected:
            module = self._modules[module_id]
            for dependency in module.dependencies:
                if dependency in selected:
                    indegree[module_id] += 1
                    dependents[dependency].add(module_id)

        def sort_key(module_id: str) -> tuple[str, str]:
            module = self._modules[module_id]
            return module.stage_number, module.module_id

        ready = sorted(
            (module_id for module_id, degree in indegree.items() if degree == 0),
            key=sort_key,
        )
        ordered: list[str] = []
        while ready:
            module_id = ready.pop(0)
            ordered.append(module_id)
            for dependent in sorted(dependents[module_id], key=sort_key):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort(key=sort_key)
        if len(ordered) != len(selected):
            cyclic = sorted(
                (module_id for module_id, degree in indegree.items() if degree > 0),
                key=sort_key,
            )
            raise WorkflowCycleError(
                "Module dependency cycle detected among: " + ", ".join(cyclic) + "."
            )
        return tuple(ordered)


class WorkflowRunner:
    """Plan and execute registered V2 handlers sequentially."""

    def __init__(
        self,
        *,
        catalog: ModuleCatalog = DEFAULT_CATALOG,
        registry: HandlerRegistry | None = None,
        publisher: TransactionalPublisher | None = None,
        reuse_index: PublishedRunIndex | None = None,
    ) -> None:
        self.catalog = catalog
        self.registry = registry if registry is not None else default_handler_registry()
        self.publisher = publisher
        self.reuse_index = reuse_index
        self.dag = WorkflowDAG(catalog)
        unknown_handlers = sorted(set(self.registry.module_ids()) - set(self.dag.all_modules_order))
        if unknown_handlers:
            raise HandlerRegistrationError(
                "Handlers are registered for unknown catalog modules: "
                + ", ".join(unknown_handlers)
                + "."
            )

    def plan(
        self,
        requested_modules: str | Iterable[str],
        *,
        context: RunContext | None = None,
        reuse_index: PublishedRunIndex | None = None,
    ) -> WorkflowPlan:
        requested = self._normalize_requested(requested_modules)
        order = self.dag.execution_order(requested)
        entries: list[PlanEntry] = []
        status_by_module: dict[str, PlanStatus] = {}
        selections: dict[str, ReuseSelection] = {}
        selected_index = reuse_index if reuse_index is not None else self.reuse_index
        if selected_index is not None and context is None:
            raise WorkflowError("Reuse-aware planning requires a RunContext.")
        references = (
            selected_index.candidates_for(context)
            if selected_index is not None and context is not None
            else ()
        )
        for module_id in order:
            module = self.catalog.by_id(module_id)
            unavailable_dependencies = tuple(
                dependency
                for dependency in module.dependencies
                if status_by_module.get(dependency)
                in {PlanStatus.NOT_IMPLEMENTED, PlanStatus.BLOCKED}
            )
            if not self.registry.has(module_id):
                status = PlanStatus.NOT_IMPLEMENTED
                reason = "No V2 handler is registered for this known module."
                reason_code = "handler_not_implemented"
                reason_details: dict[str, Any] = {}
            elif unavailable_dependencies:
                status = PlanStatus.BLOCKED
                reason = (
                    "Required dependencies are not ready: "
                    + ", ".join(unavailable_dependencies)
                    + "."
                )
                reason_code = "dependency_blocked"
                reason_details = {"dependencies": list(unavailable_dependencies)}
            elif not references:
                status = PlanStatus.READY
                reason = "Registered handler and required dependencies are ready."
                reason_code = "candidate_absent"
                reason_details = {}
            else:
                non_reusable_dependencies = tuple(
                    dependency
                    for dependency in module.dependencies
                    if status_by_module.get(dependency) is not PlanStatus.REUSABLE
                )
                if non_reusable_dependencies:
                    status = PlanStatus.INVALIDATED
                    reason = (
                        "Upstream results must be recomputed: "
                        + ", ".join(non_reusable_dependencies)
                        + "."
                    )
                    reason_code = "upstream_invalidated"
                    reason_details = {
                        "dependencies": list(non_reusable_dependencies)
                    }
                elif self.publisher is None or context is None:
                    status = PlanStatus.INVALIDATED
                    reason = "Published candidates cannot be verified without a publisher."
                    reason_code = "publication_unavailable"
                    reason_details = {}
                else:
                    dependency_hashes = {
                        dependency: selections[dependency].module_content_hash
                        for dependency in module.dependencies
                    }
                    expected = expected_provenance(
                        context,
                        module_id,
                        self.registry.registration(module_id),
                        dependency_hashes,
                    )
                    check = select_reusable_module(
                        output_root=self.publisher.output_root,
                        references=references,
                        module_id=module_id,
                        expected=expected,
                        allow_best_effort=self.registry.registration(
                            module_id
                        ).allow_best_effort_reuse,
                    )
                    reason = check.reason.message
                    reason_code = check.reason.code
                    reason_details = dict(check.reason.details)
                    if check.selection is not None:
                        status = PlanStatus.REUSABLE
                        selections[module_id] = check.selection
                    else:
                        status = PlanStatus.INVALIDATED
            status_by_module[module_id] = status
            entries.append(
                PlanEntry(
                    module_id=module_id,
                    stage_number=module.stage_number,
                    status=status,
                    reason=reason,
                    required_dependencies=module.dependencies,
                    reason_code=reason_code,
                    reason_details=reason_details,
                )
            )
        return WorkflowPlan(requested, order, tuple(entries), selections)

    def run(
        self,
        context: RunContext,
        requested_modules: str | Iterable[str],
    ) -> WorkflowRunResult:
        if not isinstance(context, RunContext):
            raise TypeError("context must be a RunContext instance.")
        if self.publisher is None:
            raise WorkflowError("Workflow run requires the V2 TransactionalPublisher.")
        plan = self.plan(requested_modules, context=context)
        results_by_module: dict[str, StageResult] = {}
        outputs_by_module: dict[str, HandlerOutput] = {}

        for module_id in plan.execution_order:
            module = self.catalog.by_id(module_id)
            if module_id in plan.reuse_selections:
                selection = plan.reuse_selections[module_id]
                result = replace(
                    selection.result,
                    metadata={
                        **selection.result.metadata,
                        "reused_from": {
                            "project_id": selection.reference.project_id,
                            "design_revision": selection.reference.design_revision,
                            "case_id": selection.reference.case_id,
                            "run_id": selection.reference.run_id,
                            "manifest_sha256": selection.reference.manifest_sha256,
                        },
                    },
                )
                results_by_module[module_id] = result
                outputs_by_module[module_id] = HandlerOutput(
                    result,
                    selection.artifact_bytes,
                )
                continue
            blocking = tuple(
                dependency
                for dependency in module.dependencies
                if results_by_module[dependency].execution_status
                is not ExecutionStatus.COMPLETED
            )
            if blocking:
                result = self._status_result(
                    module,
                    ExecutionStatus.BLOCKED,
                    code="upstream_blocked",
                    message="Blocked by upstream modules: " + ", ".join(blocking) + ".",
                )
                results_by_module[module_id] = result
                continue
            if not self.registry.has(module_id):
                result = self._status_result(
                    module,
                    ExecutionStatus.NOT_IMPLEMENTED,
                    code="handler_not_implemented",
                    message="No V2 handler is registered for this known module.",
                )
                results_by_module[module_id] = result
                continue

            dependency_results = {
                dependency: results_by_module[dependency]
                for dependency in module.dependencies
            }
            dependency_hashes: dict[str, str] = {}
            provenance_available = True
            for dependency, dependency_result in dependency_results.items():
                try:
                    dependency_hashes[dependency] = module_content_hash(
                        dependency_result.artifacts
                    )
                except ContractError:
                    provenance_available = False
                    break
            expected = (
                expected_provenance(
                    context,
                    module_id,
                    self.registry.registration(module_id),
                    dependency_hashes,
                )
                if provenance_available
                else None
            )
            request = StageExecutionRequest(
                context,
                module,
                dependency_results,
                expected,
            )
            try:
                raw_output = self.registry.get(module_id)(request)
                output = self._normalize_handler_output(
                    module,
                    raw_output,
                    expected_provenance_signature=(
                        expected.signature if expected is not None else None
                    ),
                )
            except Exception as exc:
                result = self._status_result(
                    module,
                    ExecutionStatus.FAILED,
                    code="handler_failed",
                    message=f"Handler raised {type(exc).__name__}: {exc}",
                )
                results_by_module[module_id] = result
                continue
            results_by_module[module_id] = output.result
            outputs_by_module[module_id] = output

        ordered_results = tuple(
            results_by_module[module_id] for module_id in plan.execution_order
        )
        published_path: str | None = None
        if all(result.execution_status is ExecutionStatus.COMPLETED for result in ordered_results):
            path = self.publisher.publish(
                context,
                ordered_results,
                lambda transaction: self._write_outputs(
                    transaction,
                    plan.execution_order,
                    outputs_by_module,
                ),
            )
            published_path = str(path)
        return WorkflowRunResult(
            context=context,
            requested_modules=plan.requested_modules,
            execution_order=plan.execution_order,
            stage_results=ordered_results,
            published_path=published_path,
        )

    def _normalize_requested(
        self,
        requested_modules: str | Iterable[str],
    ) -> tuple[str, ...]:
        requested = (
            (requested_modules,)
            if isinstance(requested_modules, str)
            else tuple(requested_modules)
        )
        if not requested:
            raise WorkflowError("At least one semantic module_id must be requested.")
        if not all(isinstance(module_id, str) for module_id in requested):
            raise WorkflowError("Requested modules must be semantic module_id strings.")
        duplicates = {item for item in requested if requested.count(item) > 1}
        if duplicates:
            raise WorkflowError(
                "Duplicate requested module IDs: " + ", ".join(sorted(duplicates)) + "."
            )
        for module_id in requested:
            if module_id not in {item.module_id for item in self.catalog.modules}:
                raise WorkflowError(
                    f"Unknown semantic module_id {module_id!r}; numeric and V1 aliases "
                    "are not accepted."
                )
        return tuple(
            sorted(
                requested,
                key=lambda module_id: (
                    self.catalog.by_id(module_id).stage_number,
                    module_id,
                ),
            )
        )

    def _normalize_handler_output(
        self,
        module: ModuleDefinition,
        raw_output: HandlerOutput | StageResult,
        *,
        expected_provenance_signature: str | None = None,
    ) -> HandlerOutput:
        output = raw_output if isinstance(raw_output, HandlerOutput) else HandlerOutput(raw_output)
        result = output.result
        if (result.module_id, result.stage_number) != (module.module_id, module.stage_number):
            raise ContractError(
                f"Handler for {module.module_id!r} returned another module identity."
            )
        declared = {artifact.uri: artifact for artifact in result.artifacts}
        actual = dict(output.artifact_bytes)
        if set(declared) != set(actual):
            raise ContractError(
                f"Handler for {module.module_id!r} did not return exactly its declared artifacts."
            )
        for uri, manifest in declared.items():
            digest = hashlib.sha256(actual[uri]).hexdigest()
            if digest != manifest.sha256:
                raise ContractError(
                    f"Handler artifact {manifest.artifact_id!r} has a SHA-256 mismatch."
                )
        if result.execution_status is not ExecutionStatus.COMPLETED and actual:
            raise ContractError("A non-completed handler cannot stage publishable artifacts.")
        if expected_provenance_signature is not None:
            if not result.artifacts:
                raise ContractError(
                    "A reuse-enabled handler must publish provenance-bearing artifacts."
                )
            signatures = {
                artifact.provenance.signature
                for artifact in result.artifacts
                if artifact.provenance is not None
            }
            if signatures != {expected_provenance_signature} or any(
                artifact.provenance is None for artifact in result.artifacts
            ):
                raise ContractError(
                    "Handler artifacts do not match the expected process provenance."
                )
        return output

    @staticmethod
    def _write_outputs(
        transaction: PublicationTransaction,
        execution_order: tuple[str, ...],
        outputs_by_module: Mapping[str, HandlerOutput],
    ) -> None:
        for module_id in execution_order:
            output = outputs_by_module[module_id]
            for uri in sorted(output.artifact_bytes):
                transaction.write_bytes(uri, output.artifact_bytes[uri])

    @staticmethod
    def _status_result(
        module: ModuleDefinition,
        status: ExecutionStatus,
        *,
        code: str,
        message: str,
    ) -> StageResult:
        return StageResult(
            schema_version="2",
            module_id=module.module_id,
            stage_number=module.stage_number,
            execution_status=status,
            numerical_quality=NumericalQualityStatus.NOT_EVALUATED,
            applicability=ApplicabilityStatus.NOT_EVALUATED,
            performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
            errors=(StageMessage(code, message),),
        )


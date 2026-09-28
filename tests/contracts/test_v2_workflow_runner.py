"""V2-015 sequential workflow planning, execution, and publication tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ArtifactManifest,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    StageResult,
)
from structurelab_pbd_rc.core.exceptions import (
    DependencyError,
    PublicationCollisionError,
    WorkflowCycleError,
)
from structurelab_pbd_rc.io.artifacts import TransactionalPublisher
from structurelab_pbd_rc.workflow.catalog import ModuleCatalog, ModuleDefinition
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.registry import (
    HandlerOutput,
    HandlerRegistry,
    StageExecutionRequest,
    default_handler_registry,
)
from structurelab_pbd_rc.workflow.runner import PlanStatus, WorkflowDAG, WorkflowRunner


def chain_catalog() -> ModuleCatalog:
    """Small canonical-identity graph used only by infrastructure doubles."""

    return ModuleCatalog(
        (
            ModuleDefinition("03", "material_characterization", "Independent"),
            ModuleDefinition("02", "baseline_model", "Leaf", ("site_hazard",)),
            ModuleDefinition("00", "project_objectives", "Root"),
            ModuleDefinition("01", "site_hazard", "Middle", ("project_objectives",)),
        )
    )


def context(tmp_path: Path, *, run_id: str = "run_001") -> RunContext:
    return RunContext(
        schema_version="2",
        run_id=run_id,
        project_id="tower_a",
        design_revision="rev_01",
        case_id="case_01",
        project_root=str(tmp_path.resolve()),
        code_version="0.1.0",
        environment={"runner": "test_double"},
        resolved_configuration={"test": True},
    )


def successful_handler(
    *,
    with_artifact: bool = False,
) -> Callable[[StageExecutionRequest], HandlerOutput]:
    def handler(request: StageExecutionRequest) -> HandlerOutput:
        artifacts: tuple[ArtifactManifest, ...] = ()
        artifact_bytes: dict[str, bytes] = {}
        if with_artifact:
            payload = json.dumps(
                {
                    "module_id": request.module.module_id,
                    "run_id": request.context.run_id,
                },
                sort_keys=True,
            ).encode("utf-8")
            uri = (
                f"{request.module.stage_number}_{request.module.module_id}"
                "/data/test_output.json"
            )
            artifacts = (
                ArtifactManifest(
                    schema_version="2",
                    artifact_id=f"{request.module.module_id}_test_output",
                    artifact_type="test_output",
                    module_id=request.module.module_id,
                    stage_number=request.module.stage_number,
                    producer="tests.v2_workflow_runner",
                    uri=uri,
                    sha256=hashlib.sha256(payload).hexdigest(),
                ),
            )
            artifact_bytes[uri] = payload
        result = StageResult(
            schema_version="2",
            module_id=request.module.module_id,
            stage_number=request.module.stage_number,
            execution_status=ExecutionStatus.COMPLETED,
            numerical_quality=NumericalQualityStatus.CONVERGED,
            applicability=ApplicabilityStatus.APPLICABLE,
            performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
            artifacts=artifacts,
        )
        return HandlerOutput(result, artifact_bytes)

    return handler


def failing_handler(request: StageExecutionRequest) -> HandlerOutput:
    raise RuntimeError(f"failure in {request.module.module_id}")


def registry_for(*module_ids: str, with_artifact: bool = False) -> HandlerRegistry:
    registry = HandlerRegistry()
    for module_id in module_ids:
        registry.register(module_id, successful_handler(with_artifact=with_artifact))
    return registry


def test_valid_dag_and_deterministic_topological_order() -> None:
    dag = WorkflowDAG(chain_catalog())
    expected = (
        "project_objectives",
        "site_hazard",
        "baseline_model",
        "material_characterization",
    )
    assert dag.all_modules_order == expected
    assert dag.execution_order(reversed(expected)) == expected


def test_cycle_is_rejected_before_execution() -> None:
    catalog = ModuleCatalog(
        (
            ModuleDefinition("00", "project_objectives", "A", ("site_hazard",)),
            ModuleDefinition("01", "site_hazard", "B", ("project_objectives",)),
        )
    )
    with pytest.raises(WorkflowCycleError, match="cycle"):
        WorkflowDAG(catalog)


def test_missing_dependency_is_rejected_by_catalog_boundary() -> None:
    with pytest.raises(DependencyError, match="unknown dependency"):
        ModuleCatalog(
            (
                ModuleDefinition(
                    "00",
                    "project_objectives",
                    "Root",
                    ("site_hazard",),
                ),
            )
        )


def test_partial_selection_and_transitive_dependencies() -> None:
    runner = WorkflowRunner(catalog=chain_catalog(), registry=HandlerRegistry())
    assert runner.plan("project_objectives").execution_order == (
        "project_objectives",
    )
    assert runner.plan(("baseline_model",)).execution_order == (
        "project_objectives",
        "site_hazard",
        "baseline_model",
    )
    assert runner.plan(
        ("material_characterization", "baseline_model")
    ).execution_order == (
        "project_objectives",
        "site_hazard",
        "baseline_model",
        "material_characterization",
    )


def test_plan_distinguishes_ready_not_implemented_and_blocked() -> None:
    registry = registry_for("project_objectives", "baseline_model")
    plan = WorkflowRunner(catalog=chain_catalog(), registry=registry).plan(
        ("baseline_model",)
    )
    assert plan.entry("project_objectives").status is PlanStatus.READY
    assert plan.entry("site_hazard").status is PlanStatus.NOT_IMPLEMENTED
    blocked = plan.entry("baseline_model")
    assert blocked.status is PlanStatus.BLOCKED
    assert blocked.required_dependencies == ("site_hazard",)
    assert "site_hazard" in blocked.reason


def test_registry_only_exposes_scientific_handlers_migrated_to_v2() -> None:
    registry = default_handler_registry()
    assert registry.module_ids() == (
        "material_characterization",
        "project_objectives",
        "section_component_characterization",
        "site_hazard",
    )
    plan = WorkflowRunner(registry=registry).plan(("ground_motion",))
    assert plan.entry("project_objectives").status is PlanStatus.READY
    assert plan.entry("site_hazard").status is PlanStatus.READY
    assert plan.entry("ground_motion").status is PlanStatus.NOT_IMPLEMENTED
    assert "baseline_model" not in plan.execution_order


def test_workflow_plan_is_a_filesystem_side_effect_free_dry_run(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    runner = WorkflowRunner(
        catalog=chain_catalog(),
        registry=registry_for("project_objectives"),
        publisher=TransactionalPublisher(output_root),
    )
    plan = runner.plan(("baseline_model",))
    assert plan.execution_order[-1] == "baseline_model"
    assert not output_root.exists()


def test_known_unimplemented_module_never_completes_or_publishes(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    runner = WorkflowRunner(
        catalog=chain_catalog(),
        registry=registry_for("project_objectives"),
        publisher=publisher,
    )
    outcome = runner.run(context(tmp_path), ("site_hazard",))
    assert outcome.result("project_objectives").completed is True
    assert (
        outcome.result("site_hazard").execution_status
        is ExecutionStatus.NOT_IMPLEMENTED
    )
    assert outcome.published_path is None
    assert not publisher.final_path(context(tmp_path)).exists()


def test_upstream_failure_blocks_downstream_and_keeps_prior_result_valid(
    tmp_path: Path,
) -> None:
    registry = registry_for("project_objectives", "baseline_model")
    registry.register("site_hazard", failing_handler)
    publisher = TransactionalPublisher(tmp_path / "outputs")
    runner = WorkflowRunner(
        catalog=chain_catalog(), registry=registry, publisher=publisher
    )
    outcome = runner.run(context(tmp_path), ("baseline_model",))
    assert outcome.result("project_objectives").completed is True
    assert outcome.result("site_hazard").execution_status is ExecutionStatus.FAILED
    assert outcome.result("baseline_model").execution_status is ExecutionStatus.BLOCKED
    assert outcome.result("baseline_model").errors[0].code == "upstream_blocked"
    assert outcome.published_path is None
    assert not publisher.final_path(context(tmp_path)).exists()


def test_completed_stage_is_not_implicitly_accepted(tmp_path: Path) -> None:
    runner = WorkflowRunner(
        catalog=chain_catalog(),
        registry=registry_for("project_objectives"),
        publisher=TransactionalPublisher(tmp_path / "outputs"),
    )
    outcome = runner.run(context(tmp_path), ("project_objectives",))
    result = outcome.result("project_objectives")
    assert result.completed is True
    assert result.accepted is False
    assert (
        result.performance_acceptance
        is PerformanceAcceptanceStatus.NOT_EVALUATED
    )


def test_runner_integrates_only_through_transactional_publication(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "outputs"
    publisher = TransactionalPublisher(output_root)
    runner = WorkflowRunner(
        catalog=chain_catalog(),
        registry=registry_for(
            "project_objectives", "site_hazard", "baseline_model", with_artifact=True
        ),
        publisher=publisher,
    )
    outcome = runner.run(context(tmp_path), ("baseline_model",))
    final = publisher.final_path(context(tmp_path))
    assert outcome.published_path == str(final)
    manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    assert [item["module_id"] for item in manifest["stage_results"]] == list(
        outcome.execution_order
    )
    assert len(manifest["artifacts"]) == 3
    for artifact in manifest["artifacts"]:
        assert (final / artifact["uri"]).is_file()


def test_two_run_ids_are_isolated(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    runner = WorkflowRunner(
        catalog=chain_catalog(),
        registry=registry_for("project_objectives", with_artifact=True),
        publisher=publisher,
    )
    first = runner.run(context(tmp_path, run_id="run_001"), ("project_objectives",))
    second = runner.run(context(tmp_path, run_id="run_002"), ("project_objectives",))
    assert first.published_path != second.published_path
    assert Path(first.published_path or "").is_dir()
    assert Path(second.published_path or "").is_dir()


def test_published_run_is_immutable_through_runner(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    runner = WorkflowRunner(
        catalog=chain_catalog(),
        registry=registry_for("project_objectives", with_artifact=True),
        publisher=publisher,
    )
    run_context = context(tmp_path)
    first = runner.run(run_context, ("project_objectives",))
    final = Path(first.published_path or "")
    before = (final / "manifest.json").read_bytes()
    with pytest.raises(PublicationCollisionError, match="immutable"):
        runner.run(run_context, ("project_objectives",))
    assert (final / "manifest.json").read_bytes() == before


def test_runner_never_modifies_v1_outputs(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    sentinel = output_root / "stage_01" / "existing_v1.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"frozen-v1")
    before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    runner = WorkflowRunner(
        catalog=chain_catalog(),
        registry=registry_for("project_objectives", with_artifact=True),
        publisher=TransactionalPublisher(output_root),
    )
    runner.run(context(tmp_path), ("project_objectives",))
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == before
    assert sorted(path.name for path in output_root.iterdir()) == ["stage_01", "v2"]

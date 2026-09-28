"""Runtime handler registry, intentionally separate from the module catalog."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from importlib.metadata import version as package_version
from types import MappingProxyType

from structurelab_pbd_rc.contracts import (
    ArtifactManifest,
    ProcessProvenance,
    ProjectSpec,
    StageResult,
)
from structurelab_pbd_rc.contracts._common import validate_identifier
from structurelab_pbd_rc.core.exceptions import ContractError, HandlerRegistrationError
from structurelab_pbd_rc.workflow.catalog import ModuleDefinition
from structurelab_pbd_rc.workflow.context import RunContext


@dataclass(frozen=True)
class StageExecutionRequest:
    """Inputs visible to one registered handler during a sequential run."""

    context: RunContext
    module: ModuleDefinition
    dependency_results: Mapping[str, StageResult]
    expected_provenance: ProcessProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dependency_results",
            MappingProxyType(dict(self.dependency_results)),
        )


@dataclass(frozen=True)
class HandlerOutput:
    """A StageResult plus in-memory bytes for its declared artifacts."""

    result: StageResult
    artifact_bytes: Mapping[str, bytes] = field(default_factory=dict)

    def __post_init__(self) -> None:
        values = dict(self.artifact_bytes)
        if not all(
            isinstance(uri, str) and uri and isinstance(content, bytes)
            for uri, content in values.items()
        ):
            raise ContractError("Handler artifact_bytes must map non-empty URIs to bytes.")
        object.__setattr__(self, "artifact_bytes", MappingProxyType(values))


StageHandler = Callable[[StageExecutionRequest], HandlerOutput | StageResult]


@dataclass(frozen=True)
class HandlerRegistration:
    """Implementation identity and conservative reuse policy for one handler."""

    handler: StageHandler
    implementation_version: str | None = None
    backend_version: str | None = None
    units: Mapping[str, str] = field(default_factory=dict)
    sign_conventions: Mapping[str, str] = field(default_factory=dict)
    required_input_ids: tuple[str, ...] = ()
    configuration_path: tuple[str, ...] | None = None
    reuse_allowed: bool = False
    allow_best_effort_reuse: bool = False

    def __post_init__(self) -> None:
        for name in ("implementation_version", "backend_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ContractError(f"{name} must be a non-empty string when provided.")
        for name in ("units", "sign_conventions"):
            values = dict(getattr(self, name))
            if not all(
                isinstance(key, str)
                and key.strip()
                and isinstance(value, str)
                and value.strip()
                for key, value in values.items()
            ):
                raise ContractError(f"{name} must be a string-to-string mapping.")
            object.__setattr__(self, name, MappingProxyType(values))
        object.__setattr__(self, "required_input_ids", tuple(self.required_input_ids))
        for input_id in self.required_input_ids:
            validate_identifier(input_id, name="required_input_id")
        if len(set(self.required_input_ids)) != len(self.required_input_ids):
            raise ContractError("required_input_ids cannot contain duplicates.")
        if self.configuration_path is not None:
            object.__setattr__(self, "configuration_path", tuple(self.configuration_path))
            if not self.configuration_path or not all(
                isinstance(item, str) and item for item in self.configuration_path
            ):
                raise ContractError("configuration_path must contain non-empty keys.")
        if not isinstance(self.reuse_allowed, bool):
            raise ContractError("reuse_allowed must be boolean.")
        if not isinstance(self.allow_best_effort_reuse, bool):
            raise ContractError("allow_best_effort_reuse must be boolean.")
        if self.allow_best_effort_reuse and not self.reuse_allowed:
            raise ContractError(
                "allow_best_effort_reuse requires reuse_allowed=true."
            )


class HandlerRegistry:
    """Availability registry; catalog membership alone never implies a handler."""

    def __init__(self) -> None:
        self._registrations: dict[str, HandlerRegistration] = {}

    def register(
        self,
        module_id: str,
        handler: StageHandler,
        *,
        overwrite: bool = False,
        implementation_version: str | None = None,
        backend_version: str | None = None,
        units: Mapping[str, str] | None = None,
        sign_conventions: Mapping[str, str] | None = None,
        required_input_ids: tuple[str, ...] = (),
        configuration_path: tuple[str, ...] | None = None,
        reuse_allowed: bool = False,
        allow_best_effort_reuse: bool = False,
    ) -> StageHandler:
        validate_identifier(module_id, name="module_id", semantic=True)
        if not callable(handler):
            raise HandlerRegistrationError("A stage handler must be callable.")
        if module_id in self._registrations and not overwrite:
            raise HandlerRegistrationError(
                f"Handler for module {module_id!r} is already registered."
            )
        self._registrations[module_id] = HandlerRegistration(
            handler=handler,
            implementation_version=implementation_version,
            backend_version=backend_version,
            units=units or {},
            sign_conventions=sign_conventions or {},
            required_input_ids=required_input_ids,
            configuration_path=configuration_path,
            reuse_allowed=reuse_allowed,
            allow_best_effort_reuse=allow_best_effort_reuse,
        )
        return handler

    def has(self, module_id: str) -> bool:
        return module_id in self._registrations

    def get(self, module_id: str) -> StageHandler:
        try:
            return self._registrations[module_id].handler
        except KeyError as exc:
            raise HandlerRegistrationError(
                f"No handler is registered for module {module_id!r}."
            ) from exc

    def module_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._registrations))

    def registration(self, module_id: str) -> HandlerRegistration:
        try:
            return self._registrations[module_id]
        except KeyError as exc:
            raise HandlerRegistrationError(
                f"No handler is registered for module {module_id!r}."
            ) from exc


def _project_objectives_handler(request: StageExecutionRequest) -> HandlerOutput:
    from structurelab_pbd_rc.workflow.stages.project_objectives import (
        evaluate_project_objectives,
    )

    resolved = request.context.resolved_configuration
    raw_project = resolved.get("project_spec", resolved)
    if not isinstance(raw_project, Mapping):
        raise ContractError("RunContext project_spec must be a mapping.")
    project = ProjectSpec.from_dict(dict(raw_project))
    identity = (project.project_id, project.design_revision, project.case_id)
    context_identity = (
        request.context.project_id,
        request.context.design_revision,
        request.context.case_id,
    )
    if identity != context_identity:
        raise ContractError("ProjectSpec identity does not match RunContext identity.")
    content = project.to_json(indent=2).encode("utf-8")
    declared_hashes = request.context.metadata.get("input_hashes", {})
    if isinstance(declared_hashes, Mapping):
        project_hashes = declared_hashes.get("project_objectives", {})
        if isinstance(project_hashes, Mapping) and "project_spec" in project_hashes:
            if project_hashes["project_spec"] != hashlib.sha256(content).hexdigest():
                raise ContractError("Resolved ProjectSpec does not match its declared input hash.")
    artifact = ArtifactManifest(
        schema_version="2",
        artifact_id="project_spec",
        artifact_type="project_spec",
        module_id="project_objectives",
        stage_number="00",
        producer="structurelab_pbd_rc.workflow.registry.project_objectives",
        uri="00_project_objectives/data/project_spec.json",
        sha256=hashlib.sha256(content).hexdigest(),
        units={
            "length": project.base_units.length,
            "force": project.base_units.force,
            "time": project.base_units.time,
        },
        provenance=request.expected_provenance,
    )
    result = replace(evaluate_project_objectives(project), artifacts=(artifact,))
    return HandlerOutput(result, {artifact.uri: content})


def default_handler_registry() -> HandlerRegistry:
    """Return handlers for Stage 00 and migrated V2 scientific capabilities."""

    from structurelab_pbd_rc.workflow.stages.material_characterization import (
        execute_material_characterization,
    )
    from structurelab_pbd_rc.workflow.stages.section_component_characterization import (
        IMPLEMENTATION_VERSION as SECTION_IMPLEMENTATION_VERSION,
        execute_section_component_characterization,
    )
    from structurelab_pbd_rc.workflow.stages.site_hazard import execute_site_hazard

    registry = HandlerRegistry()
    registry.register(
        "project_objectives",
        _project_objectives_handler,
        implementation_version="v2-011.1",
        required_input_ids=("project_spec",),
        configuration_path=("project_spec",),
        reuse_allowed=True,
    )
    registry.register(
        "site_hazard",
        execute_site_hazard,
        implementation_version="spectra-kernel-v1+service-v2-017.1",
        units={"period": "s", "spectral_acceleration": "g"},
        sign_conventions={"spectral_acceleration": "unsigned_nonnegative"},
        required_input_ids=("hazard_configuration",),
        configuration_path=("module_inputs", "site_hazard"),
        reuse_allowed=True,
    )
    registry.register(
        "material_characterization",
        execute_material_characterization,
        implementation_version="material-kernels-v1+service-v2-018+publication-v2-019.1",
        backend_version=f"matplotlib-{package_version('matplotlib')}",
        units={
            "length": "mm",
            "strain": "mm/mm",
            "stress": "MPa",
            "tangent": "MPa",
        },
        sign_conventions={
            "strain": "model_declared_native",
            "stress": "model_declared_native",
            "tangent": "not_applicable",
        },
        required_input_ids=("material_configuration",),
        configuration_path=("module_inputs", "material_characterization"),
        reuse_allowed=True,
    )
    registry.register(
        "section_component_characterization",
        execute_section_component_characterization,
        implementation_version=SECTION_IMPLEMENTATION_VERSION,
        backend_version=f"matplotlib-{package_version('matplotlib')}",
        units={
            "curvature": "1/m",
            "moment": "kN-m",
            "effective_stiffness": "kN-m^2",
            "area_under_M_phi": "kN",
        },
        sign_conventions={
            "curvature": "positive_along_axis",
            "moment": "positive_about_axis",
        },
        required_input_ids=("section_configuration",),
        configuration_path=("module_inputs", "section_component_characterization"),
        reuse_allowed=True,
        allow_best_effort_reuse=True,
    )
    return registry


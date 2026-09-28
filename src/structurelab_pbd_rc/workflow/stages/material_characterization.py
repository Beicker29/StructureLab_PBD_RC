"""V2 handler for material characterization, presentation, and publication."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ArtifactDependency,
    ArtifactManifest,
    BoundaryDefinition,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    PhysicalQuantity,
    ProjectSpec,
    ReferenceSystem,
    SignConvention,
    StageMessage,
    StageResult,
)
from structurelab_pbd_rc.contracts._common import validate_identifier
from structurelab_pbd_rc.core.exceptions import ContractError
from structurelab_pbd_rc.presentation.material_characterization import (
    PresentationArtifact,
    build_material_tables,
    render_material_figures,
)
from structurelab_pbd_rc.services.material_evaluation import (
    MaterialEvaluationInput,
    MaterialEvaluationResult,
    MaterialEvaluationService,
)
from structurelab_pbd_rc.workflow.registry import HandlerOutput, StageExecutionRequest


MODULE_ID = "material_characterization"
STAGE_NUMBER = "03"
PRODUCER = "structurelab_pbd_rc.workflow.stages.material_characterization"
MATERIAL_EVALUATION_SERVICE = MaterialEvaluationService()


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _plain(value),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _resolved_project(configuration: Mapping[str, Any]) -> ProjectSpec:
    raw = configuration.get("project_spec", configuration)
    if not isinstance(raw, Mapping):
        raise ContractError("RunContext project_spec must be a mapping.")
    return ProjectSpec.from_dict(dict(raw))


def _material_configuration(configuration: Mapping[str, Any]) -> dict[str, Any]:
    module_inputs = configuration.get("module_inputs")
    if not isinstance(module_inputs, Mapping):
        raise ContractError(
            "RunContext must declare module_inputs for material_characterization."
        )
    raw = module_inputs.get(MODULE_ID)
    if not isinstance(raw, Mapping):
        raise ContractError(
            "RunContext has no structured material_characterization input."
        )
    config = dict(raw)
    unknown = sorted(set(config) - {"schema_version", "material_set_id", "models"})
    if unknown:
        raise ContractError(
            "Unknown material_characterization fields: " + ", ".join(unknown) + "."
        )
    if config.get("schema_version") != "2":
        raise ContractError("Material characterization schema_version must be '2'.")
    material_set_id = config.get("material_set_id")
    if not isinstance(material_set_id, str):
        raise ContractError("A single material_set_id is required.")
    validate_identifier(material_set_id, name="material_set_id")
    models = config.get("models")
    if not isinstance(models, list) or not models:
        raise ContractError("material_characterization.models must be a non-empty list.")
    return config


def _input_hash(request: StageExecutionRequest) -> str:
    all_hashes = request.context.metadata.get("input_hashes", {})
    if not isinstance(all_hashes, Mapping):
        raise ContractError("RunContext input_hashes metadata is missing.")
    module_hashes = all_hashes.get(MODULE_ID, {})
    if not isinstance(module_hashes, Mapping):
        raise ContractError("RunContext material input hashes are missing.")
    value = module_hashes.get("material_configuration")
    if not isinstance(value, str):
        raise ContractError("RunContext has no material_configuration hash.")
    return value


def _boundaries(result: MaterialEvaluationResult) -> dict[str, BoundaryDefinition]:
    compression_positive = result.instance.formulation.model_id == "Mon_Mander1988"
    signed = (
        SignConvention.COMPRESSION_POSITIVE_TENSION_NEGATIVE
        if compression_positive
        else SignConvention.TENSION_POSITIVE_COMPRESSION_NEGATIVE
    )
    return {
        "strain": BoundaryDefinition(
            PhysicalQuantity.STRAIN,
            "mm/mm",
            signed,
            ReferenceSystem.MATERIAL,
        ),
        "stress": BoundaryDefinition(
            PhysicalQuantity.STRESS,
            "MPa",
            signed,
            ReferenceSystem.MATERIAL,
        ),
        "tangent": BoundaryDefinition(
            PhysicalQuantity.STRESS,
            "MPa",
            SignConvention.NOT_APPLICABLE,
            ReferenceSystem.MATERIAL,
        ),
    }


def _boundary_manifest_fields(
    boundaries: Mapping[str, BoundaryDefinition],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    return (
        {name: boundary.unit for name, boundary in boundaries.items()},
        {
            name: boundary.sign_convention.value
            for name, boundary in boundaries.items()
        },
        {
            "reference_system": ReferenceSystem.MATERIAL.value,
            "axis": "uniaxial_material",
        },
    )


def _manifest(
    *,
    artifact_id: str,
    artifact_type: str,
    uri: str,
    content: bytes,
    request: StageExecutionRequest,
    dependencies: tuple[ArtifactDependency, ...],
    boundaries: Mapping[str, BoundaryDefinition],
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactManifest:
    units, signs, axes = _boundary_manifest_fields(boundaries)
    return ArtifactManifest(
        schema_version="2",
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        module_id=MODULE_ID,
        stage_number=STAGE_NUMBER,
        producer=PRODUCER,
        uri=uri,
        sha256=hashlib.sha256(content).hexdigest(),
        units=units,
        sign_conventions=signs,
        axes=axes,
        dependencies=dependencies,
        metadata=_plain(metadata or {}),
        provenance=request.expected_provenance,
    )


def _request_from_entry(
    entry: Mapping[str, Any],
    *,
    expected_case_id: str,
) -> tuple[str, MaterialEvaluationInput]:
    title = entry.get("title")
    parameter_set_id = entry.get("parameter_set_id")
    material_instance_id = entry.get("material_instance_id")
    resolved = entry.get("resolved_inputs")
    if not isinstance(title, str) or not title.strip():
        raise ContractError("Every material model requires a non-empty title.")
    if not isinstance(parameter_set_id, str):
        raise ContractError("Every material model requires parameter_set_id.")
    if not isinstance(material_instance_id, str):
        raise ContractError("Every material model requires material_instance_id.")
    validate_identifier(parameter_set_id, name="parameter_set_id")
    validate_identifier(material_instance_id, name="material_instance_id")
    if not isinstance(resolved, Mapping):
        raise ContractError("Every material model requires resolved_inputs.")
    service_input = MaterialEvaluationInput.from_resolved_inputs(
        resolved,
        parameter_set_id=parameter_set_id,
        material_instance_id=material_instance_id,
    )
    if service_input.case_id != expected_case_id:
        raise ContractError(
            "Material resolved input case_id does not match RunContext case_id."
        )
    return title, service_input


def _scientific_payload(
    result: MaterialEvaluationResult,
    boundaries: Mapping[str, BoundaryDefinition],
) -> dict[str, Any]:
    instance = result.instance
    payload: dict[str, Any] = {
        "schema_version": "2",
        "module_id": MODULE_ID,
        "stage_number": STAGE_NUMBER,
        "case_id": result.case_id,
        "evaluation_status": result.evaluation_status,
        "formulation": {
            "model_id": instance.formulation.model_id,
            "material": instance.formulation.material,
            "analysis_type": instance.formulation.analysis_type,
        },
        "parameter_set_id": instance.parameter_set.parameter_set_id,
        "material_instance_id": instance.material_instance_id,
        "provenance": _plain(instance.provenance),
        "calibration_status": instance.provenance["calibration_status"],
        "boundaries": {
            name: boundary.to_dict() for name, boundary in boundaries.items()
        },
        "curve": [_plain(row) for row in result.curve],
        "metrics": _plain(result.metrics),
        "calculated_parameters": _plain(result.calculated_parameters),
        "notable_points": [_plain(point) for point in result.notable_points],
        "warnings": list(result.warnings),
    }
    idealization = getattr(result, "idealization", None)
    if idealization is not None:
        payload["idealization"] = _plain(idealization)
    final_state = getattr(result, "final_committed_state", None)
    if final_state is not None:
        payload["final_committed_state"] = _plain(final_state)
    return payload


def _add_artifact(
    *,
    manifests: list[ArtifactManifest],
    contents: dict[str, bytes],
    request: StageExecutionRequest,
    artifact_id: str,
    artifact_type: str,
    uri: str,
    content: bytes,
    dependencies: tuple[ArtifactDependency, ...],
    boundaries: Mapping[str, BoundaryDefinition],
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactManifest:
    manifest = _manifest(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        uri=uri,
        content=content,
        request=request,
        dependencies=dependencies,
        boundaries=boundaries,
        metadata=metadata,
    )
    manifests.append(manifest)
    contents[uri] = content
    return manifest


def _add_presentation_artifact(
    artifact: PresentationArtifact,
    *,
    model_id: str,
    base_uri: str,
    request: StageExecutionRequest,
    manifests: list[ArtifactManifest],
    contents: dict[str, bytes],
    dependencies: tuple[ArtifactDependency, ...],
    boundaries: Mapping[str, BoundaryDefinition],
) -> None:
    folder = "figures" if artifact.relative_name.endswith(".png") else "tables"
    _add_artifact(
        manifests=manifests,
        contents=contents,
        request=request,
        artifact_id=f"{model_id}_{artifact.artifact_suffix}",
        artifact_type=artifact.artifact_type,
        uri=f"{base_uri}/{folder}/{artifact.relative_name}",
        content=artifact.content,
        dependencies=dependencies,
        boundaries=boundaries,
        metadata=artifact.metadata,
    )


def execute_material_characterization(request: StageExecutionRequest) -> HandlerOutput:
    """Evaluate, present, and serialize one V2 material set in isolation."""

    if request.module.module_id != MODULE_ID:
        raise ContractError(
            "material_characterization handler received another module identity."
        )
    if request.expected_provenance is None:
        raise ContractError(
            "material_characterization requires complete V2 provenance evidence."
        )
    project_result = request.dependency_results.get("project_objectives")
    if project_result is None or not project_result.completed or not project_result.artifacts:
        raise ContractError(
            "material_characterization requires a completed ProjectSpec artifact."
        )
    project = _resolved_project(request.context.resolved_configuration)
    config = _material_configuration(request.context.resolved_configuration)
    declared_input_hash = _input_hash(request)
    actual_input_hash = hashlib.sha256(_json_bytes(config)).hexdigest()
    if actual_input_hash != declared_input_hash:
        raise ContractError(
            "Resolved material configuration does not match its declared input hash."
        )
    references = tuple(
        item
        for item in project.references
        if item.module_id == MODULE_ID and item.kind in {"configuration", "input"}
    )
    if not references or not any(
        item.sha256 == declared_input_hash for item in references
    ):
        raise ContractError(
            "ProjectSpec material reference does not match the resolved input hash."
        )

    raw_entries = config["models"]
    assert isinstance(raw_entries, list)
    parsed_entries: list[tuple[str, MaterialEvaluationInput]] = []
    for entry in raw_entries:
        if not isinstance(entry, Mapping):
            raise ContractError("Every material model entry must be an object.")
        parsed_entries.append(
            _request_from_entry(entry, expected_case_id=request.context.case_id)
        )
    model_ids = [entry.instance.formulation.model_id for _, entry in parsed_entries]
    instance_ids = [entry.instance.material_instance_id for _, entry in parsed_entries]
    if len(model_ids) != len(set(model_ids)):
        raise ContractError("A material set cannot repeat a formulation model_id.")
    if len(instance_ids) != len(set(instance_ids)):
        raise ContractError("A material set cannot repeat material_instance_id.")

    evaluated = [
        (title, service_input, MATERIAL_EVALUATION_SERVICE.evaluate(service_input))
        for title, service_input in parsed_entries
    ]
    project_dependencies = tuple(
        ArtifactDependency(item.artifact_id, item.content_hash)
        for item in project_result.artifacts
    )
    manifests: list[ArtifactManifest] = []
    contents: dict[str, bytes] = {}
    stage_warnings: list[StageMessage] = []
    presentation_failures: list[dict[str, str]] = []
    calibration_statuses: dict[str, str] = {}
    numerical_quality = NumericalQualityStatus.CONVERGED
    material_set_id = str(config["material_set_id"])

    for title, service_input, result in evaluated:
        formulation = result.instance.formulation
        model_id = formulation.model_id
        calibration_statuses[model_id] = str(
            result.instance.provenance["calibration_status"]
        )
        boundaries = _boundaries(result)
        base_uri = (
            f"03_material_characterization/{material_set_id}/"
            f"{formulation.material}/{formulation.analysis_type}/{model_id}"
        )
        input_content = _json_bytes(
            {
                "schema_version": "2",
                "material_set_id": material_set_id,
                "title": title,
                "parameter_set_id": result.instance.parameter_set.parameter_set_id,
                "material_instance_id": result.instance.material_instance_id,
                "resolved_inputs": service_input.kernel_config(),
            }
        )
        input_manifest = _add_artifact(
            manifests=manifests,
            contents=contents,
            request=request,
            artifact_id=f"{model_id}_resolved_input",
            artifact_type="material_resolved_input",
            uri=f"{base_uri}/data/resolved_input.json",
            content=input_content,
            dependencies=project_dependencies,
            boundaries=boundaries,
            metadata={"source_input_sha256": declared_input_hash},
        )
        scientific_content = _json_bytes(_scientific_payload(result, boundaries))
        scientific_manifest = _add_artifact(
            manifests=manifests,
            contents=contents,
            request=request,
            artifact_id=f"{model_id}_scientific_result",
            artifact_type="material_scientific_result",
            uri=f"{base_uri}/data/scientific_result.json",
            content=scientific_content,
            dependencies=(
                ArtifactDependency(input_manifest.artifact_id, input_manifest.content_hash),
            ),
            boundaries=boundaries,
            metadata={
                "calibration_status": calibration_statuses[model_id],
                "point_count": len(result.curve),
                "evaluation_status": result.evaluation_status,
            },
        )
        result_dependencies = (
            ArtifactDependency(
                scientific_manifest.artifact_id,
                scientific_manifest.content_hash,
            ),
        )
        structured = (
            ("metrics", "material_metrics", _plain(result.metrics)),
            (
                "notable_points",
                "material_notable_points",
                {"notable_points": [_plain(point) for point in result.notable_points]},
            ),
            (
                "warnings",
                "material_warnings",
                {"warnings": list(result.warnings)},
            ),
        )
        for suffix, artifact_type, payload in structured:
            _add_artifact(
                manifests=manifests,
                contents=contents,
                request=request,
                artifact_id=f"{model_id}_{suffix}",
                artifact_type=artifact_type,
                uri=f"{base_uri}/data/{suffix}.json",
                content=_json_bytes({suffix: payload} if suffix == "metrics" else payload),
                dependencies=result_dependencies,
                boundaries=boundaries,
            )
        idealization = getattr(result, "idealization", None)
        if idealization is not None:
            status = str(idealization["status"])
            if status != "converged":
                numerical_quality = NumericalQualityStatus.BEST_EFFORT
            _add_artifact(
                manifests=manifests,
                contents=contents,
                request=request,
                artifact_id=f"{model_id}_idealization",
                artifact_type="material_idealization",
                uri=f"{base_uri}/data/idealization.json",
                content=_json_bytes({"idealization": _plain(idealization)}),
                dependencies=result_dependencies,
                boundaries=boundaries,
                metadata={"status": status},
            )
        for warning in result.warnings:
            stage_warnings.append(
                StageMessage(
                    "material_warning",
                    warning,
                    {"model_id": model_id},
                )
            )

        try:
            for artifact in build_material_tables(result):
                _add_presentation_artifact(
                    artifact,
                    model_id=model_id,
                    base_uri=base_uri,
                    request=request,
                    manifests=manifests,
                    contents=contents,
                    dependencies=result_dependencies,
                    boundaries=boundaries,
                )
        except Exception as exc:
            presentation_failures.append(
                {"model_id": model_id, "kind": "tables", "error": str(exc)}
            )
            stage_warnings.append(
                StageMessage(
                    "presentation_failed",
                    f"Table presentation failed for {model_id}: {exc}",
                    {"model_id": model_id, "kind": "tables"},
                )
            )
        try:
            for artifact in render_material_figures(result, title=title):
                _add_presentation_artifact(
                    artifact,
                    model_id=model_id,
                    base_uri=base_uri,
                    request=request,
                    manifests=manifests,
                    contents=contents,
                    dependencies=result_dependencies,
                    boundaries=boundaries,
                )
        except Exception as exc:
            presentation_failures.append(
                {"model_id": model_id, "kind": "figures", "error": str(exc)}
            )
            stage_warnings.append(
                StageMessage(
                    "presentation_failed",
                    f"Figure presentation failed for {model_id}: {exc}",
                    {"model_id": model_id, "kind": "figures"},
                )
            )

    stage_result = StageResult(
        schema_version="2",
        module_id=MODULE_ID,
        stage_number=STAGE_NUMBER,
        execution_status=ExecutionStatus.COMPLETED,
        numerical_quality=numerical_quality,
        applicability=ApplicabilityStatus.APPLICABLE,
        performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
        artifacts=tuple(manifests),
        warnings=tuple(stage_warnings),
        metadata={
            "material_set_id": material_set_id,
            "model_count": len(evaluated),
            "model_ids": model_ids,
            "calibration_statuses": calibration_statuses,
            "presentation_status": (
                "complete" if not presentation_failures else "incomplete"
            ),
            "presentation_failures": presentation_failures,
            "incomplete": bool(presentation_failures),
        },
    )
    return HandlerOutput(stage_result, contents)


__all__ = ["execute_material_characterization"]

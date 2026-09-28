"""V2 handler for imported M-phi section characterization and presentation."""

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
from structurelab_pbd_rc.core.exceptions import ContractError
from structurelab_pbd_rc.presentation.section_characterization import (
    SectionPresentationArtifact,
    build_section_tables,
    render_section_figures,
)
from structurelab_pbd_rc.services.section_characterization import (
    SectionCharacterizationInput,
    SectionCharacterizationResult,
    SectionCharacterizationService,
    SectionSheetResult,
    SectionWorksheetInput,
)
from structurelab_pbd_rc.workflow.registry import HandlerOutput, StageExecutionRequest


MODULE_ID = "section_component_characterization"
STAGE_NUMBER = "04"
PRODUCER = "structurelab_pbd_rc.workflow.stages.section_component_characterization"
IMPLEMENTATION_VERSION = (
    "moment-curvature-kernel-v1+service-v2-020+publication-v2-021.1"
)
SECTION_CHARACTERIZATION_SERVICE = SectionCharacterizationService()


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


def _section_configuration(configuration: Mapping[str, Any]) -> dict[str, Any]:
    module_inputs = configuration.get("module_inputs")
    if not isinstance(module_inputs, Mapping):
        raise ContractError(
            "RunContext must declare module_inputs for section_component_characterization."
        )
    raw = module_inputs.get(MODULE_ID)
    if not isinstance(raw, Mapping):
        raise ContractError(
            "RunContext has no structured section_component_characterization input."
        )
    config = dict(raw)
    unknown = sorted(
        set(config) - {"schema_version", "service_config", "worksheets", "source_metadata"}
    )
    if unknown:
        raise ContractError(
            "Unknown section_component_characterization fields: "
            + ", ".join(unknown)
            + "."
        )
    if config.get("schema_version") != "2":
        raise ContractError("Section characterization schema_version must be '2'.")
    if not isinstance(config.get("service_config"), Mapping):
        raise ContractError("section characterization requires service_config.")
    worksheets = config.get("worksheets")
    if not isinstance(worksheets, list) or not worksheets:
        raise ContractError("section characterization requires a non-empty worksheets list.")
    if not isinstance(config.get("source_metadata"), Mapping):
        raise ContractError("section characterization requires source_metadata.")
    return config


def _input_hash(request: StageExecutionRequest) -> str:
    all_hashes = request.context.metadata.get("input_hashes", {})
    if not isinstance(all_hashes, Mapping):
        raise ContractError("RunContext input_hashes metadata is missing.")
    module_hashes = all_hashes.get(MODULE_ID, {})
    if not isinstance(module_hashes, Mapping):
        raise ContractError("RunContext section input hashes are missing.")
    value = module_hashes.get("section_configuration")
    if not isinstance(value, str):
        raise ContractError("RunContext has no section_configuration hash.")
    return value


def _service_request(config: Mapping[str, Any]) -> SectionCharacterizationInput:
    worksheet_inputs: list[SectionWorksheetInput] = []
    raw_worksheets = config["worksheets"]
    assert isinstance(raw_worksheets, list)
    for index, raw in enumerate(raw_worksheets):
        if not isinstance(raw, Mapping):
            raise ContractError(f"worksheets[{index}] must be an object.")
        unknown = sorted(set(raw) - {"sheet_name", "rows"})
        if unknown:
            raise ContractError(
                f"Unknown worksheets[{index}] fields: {', '.join(unknown)}."
            )
        sheet_name = raw.get("sheet_name")
        rows = raw.get("rows")
        if not isinstance(sheet_name, str) or not sheet_name:
            raise ContractError(f"worksheets[{index}].sheet_name must be non-empty.")
        if not isinstance(rows, list) or not rows:
            raise ContractError(f"worksheets[{index}].rows must be a non-empty list.")
        if not all(isinstance(row, Mapping) for row in rows):
            raise ContractError(f"worksheets[{index}].rows must contain objects.")
        worksheet_inputs.append(SectionWorksheetInput.from_rows(sheet_name, rows))
    return SectionCharacterizationInput.from_resolved_inputs(
        config["service_config"],
        worksheets=worksheet_inputs,
        provenance=config["source_metadata"],
    )


def _boundaries() -> dict[str, BoundaryDefinition]:
    return {
        "curvature": BoundaryDefinition(
            PhysicalQuantity.CURVATURE,
            "1/m",
            SignConvention.POSITIVE_ALONG_AXIS,
            ReferenceSystem.SECTION_LOCAL,
            axis="section_curvature_orientation",
        ),
        "moment": BoundaryDefinition(
            PhysicalQuantity.MOMENT,
            "kN-m",
            SignConvention.POSITIVE_ABOUT_AXIS,
            ReferenceSystem.SECTION_LOCAL,
            axis="section_bending_axis",
        ),
    }


def _manifest(
    *,
    artifact_id: str,
    artifact_type: str,
    uri: str,
    content: bytes,
    request: StageExecutionRequest,
    dependencies: tuple[ArtifactDependency, ...],
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactManifest:
    boundaries = _boundaries()
    return ArtifactManifest(
        schema_version="2",
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        module_id=MODULE_ID,
        stage_number=STAGE_NUMBER,
        producer=PRODUCER,
        uri=uri,
        sha256=hashlib.sha256(content).hexdigest(),
        units={
            "curvature": boundaries["curvature"].unit,
            "moment": boundaries["moment"].unit,
            "effective_stiffness": "kN-m^2",
            "area_under_M_phi": "kN",
        },
        sign_conventions={
            name: boundary.sign_convention.value
            for name, boundary in boundaries.items()
        },
        axes={
            "reference_system": ReferenceSystem.SECTION_LOCAL.value,
            "curvature_axis": str(boundaries["curvature"].axis),
            "moment_axis": str(boundaries["moment"].axis),
        },
        dependencies=dependencies,
        metadata=_plain(metadata or {}),
        provenance=request.expected_provenance,
    )


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
    metadata: Mapping[str, Any] | None = None,
) -> ArtifactManifest:
    manifest = _manifest(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        uri=uri,
        content=content,
        request=request,
        dependencies=dependencies,
        metadata=metadata,
    )
    manifests.append(manifest)
    contents[uri] = content
    return manifest


def _scientific_payload(
    result: SectionCharacterizationResult,
    sheet: SectionSheetResult,
) -> dict[str, Any]:
    boundaries = _boundaries()
    branches: list[dict[str, Any]] = []
    for branch in sheet.branches:
        branches.append(
            {
                "curve": _plain(branch.curve),
                "source_curve": [
                    {"phi": point.phi, "moment": point.moment}
                    for point in branch.source_points
                ],
                "monotonica": _plain(branch.monotonic),
                "ciclica": _plain(branch.ciclica),
                "cut_selection": {
                    "mode": branch.cut_selection.mode,
                    "point": _plain(branch.cut_selection.point),
                    "reason": branch.cut_selection.reason,
                },
                "ciclica_reuses_monotonic": branch.ciclica_reuses_monotonic,
                "ciclica_response_semantics": branch.ciclica_response_semantics,
                "ciclica_is_hysteretic": branch.ciclica_is_hysteretic,
                "warnings": list(branch.warnings),
            }
        )
    return {
        "schema_version": "2",
        "module_id": MODULE_ID,
        "stage_number": STAGE_NUMBER,
        "sheet_name": sheet.sheet_name,
        "status": sheet.status,
        "method": result.method,
        "units": _plain(result.units),
        "boundaries": {
            name: boundary.to_dict() for name, boundary in boundaries.items()
        },
        "provenance": _plain(result.provenance),
        "branches": branches,
        "warnings": list(sheet.warnings),
        "modes": {
            "monotonica": {
                "diagram_type": sheet.monotonica.diagram_type,
                "response_semantics": sheet.monotonica.response_semantics,
                "is_hysteretic": sheet.monotonica.is_hysteretic,
                "actual_curve_rows": _plain(sheet.monotonica.actual_curve_rows),
                "bilinear_curve_rows": _plain(sheet.monotonica.bilinear_curve_rows),
                "parameter_rows": _plain(sheet.monotonica.parameter_rows),
                "warnings": list(sheet.monotonica.warnings),
            },
            "ciclica": {
                "diagram_type": sheet.ciclica.diagram_type,
                "response_semantics": sheet.ciclica.response_semantics,
                "is_hysteretic": sheet.ciclica.is_hysteretic,
                "actual_curve_rows": _plain(sheet.ciclica.actual_curve_rows),
                "bilinear_curve_rows": _plain(sheet.ciclica.bilinear_curve_rows),
                "parameter_rows": _plain(sheet.ciclica.parameter_rows),
                "cut_point_rows": _plain(sheet.ciclica.cut_point_rows),
                "warnings": list(sheet.ciclica.warnings),
            },
        },
    }


def _add_presentation_artifact(
    artifact: SectionPresentationArtifact,
    *,
    sheet_id: str,
    mode_name: str,
    base_uri: str,
    request: StageExecutionRequest,
    manifests: list[ArtifactManifest],
    contents: dict[str, bytes],
    dependencies: tuple[ArtifactDependency, ...],
) -> None:
    folder = "figures" if artifact.relative_name.endswith(".png") else "tables"
    _add_artifact(
        manifests=manifests,
        contents=contents,
        request=request,
        artifact_id=f"{sheet_id}_{artifact.artifact_suffix}",
        artifact_type=artifact.artifact_type,
        uri=f"{base_uri}/{mode_name}/{folder}/{artifact.relative_name}",
        content=artifact.content,
        dependencies=dependencies,
        metadata=artifact.metadata,
    )


def execute_section_component_characterization(
    request: StageExecutionRequest,
) -> HandlerOutput:
    """Evaluate and publish imported M-phi curves through the V2 infrastructure."""

    if request.module.module_id != MODULE_ID:
        raise ContractError("section handler received another module identity.")
    if request.expected_provenance is None:
        raise ContractError("section characterization requires complete V2 provenance evidence.")
    project_result = request.dependency_results.get("project_objectives")
    if project_result is None or not project_result.completed or not project_result.artifacts:
        raise ContractError("section characterization requires a completed ProjectSpec artifact.")
    project = _resolved_project(request.context.resolved_configuration)
    config = _section_configuration(request.context.resolved_configuration)
    declared_input_hash = _input_hash(request)
    actual_input_hash = hashlib.sha256(_json_bytes(config)).hexdigest()
    if actual_input_hash != declared_input_hash:
        raise ContractError(
            "Resolved section configuration does not match its declared input hash."
        )
    references = tuple(
        item
        for item in project.references
        if item.module_id == MODULE_ID and item.kind in {"configuration", "input"}
    )
    if not references or not any(item.sha256 == declared_input_hash for item in references):
        raise ContractError(
            "ProjectSpec section reference does not match the resolved input hash."
        )

    service_request = _service_request(config)
    result = SECTION_CHARACTERIZATION_SERVICE.evaluate(service_request)
    project_dependencies = tuple(
        ArtifactDependency(item.artifact_id, item.content_hash)
        for item in project_result.artifacts
    )
    manifests: list[ArtifactManifest] = []
    contents: dict[str, bytes] = {}
    stage_warnings: list[StageMessage] = []
    presentation_failures: list[dict[str, str]] = []
    best_effort_branches: list[str] = []
    root_uri = "04_section_component_characterization/imported_m_phi"

    input_content = _json_bytes(config)
    input_manifest = _add_artifact(
        manifests=manifests,
        contents=contents,
        request=request,
        artifact_id="section_configuration",
        artifact_type="section_resolved_input",
        uri=f"{root_uri}/data/resolved_input.json",
        content=input_content,
        dependencies=project_dependencies,
        metadata={
            "source_input_sha256": declared_input_hash,
            "source_type": "external_moment_curvature",
            "sheet_count": result.sheet_count,
        },
    )
    input_dependency = (
        ArtifactDependency(input_manifest.artifact_id, input_manifest.content_hash),
    )

    for sheet_index, sheet in enumerate(result.sheets, start=1):
        sheet_id = f"sheet_{sheet_index:02d}"
        base_uri = f"{root_uri}/{sheet_id}"
        scientific_content = _json_bytes(_scientific_payload(result, sheet))
        scientific_manifest = _add_artifact(
            manifests=manifests,
            contents=contents,
            request=request,
            artifact_id=f"{sheet_id}_scientific_result",
            artifact_type="section_scientific_result",
            uri=f"{base_uri}/data/scientific_result.json",
            content=scientific_content,
            dependencies=input_dependency,
            metadata={
                "sheet_name": sheet.sheet_name,
                "branch_count": len(sheet.branches),
                "has_best_effort": any(
                    branch.monotonic["status"] != "converged"
                    or branch.ciclica["status"] != "converged"
                    for branch in sheet.branches
                ),
                "ciclica_response_semantics": sheet.ciclica.response_semantics,
                "ciclica_is_hysteretic": False,
            },
        )
        result_dependencies = (
            ArtifactDependency(
                scientific_manifest.artifact_id,
                scientific_manifest.content_hash,
            ),
        )
        warnings_content = _json_bytes({"warnings": list(sheet.warnings)})
        _add_artifact(
            manifests=manifests,
            contents=contents,
            request=request,
            artifact_id=f"{sheet_id}_warnings",
            artifact_type="section_warnings",
            uri=f"{base_uri}/data/warnings.json",
            content=warnings_content,
            dependencies=result_dependencies,
            metadata={"warning_count": len(sheet.warnings)},
        )

        for branch in sheet.branches:
            for mode_name, mechanics in (
                ("monotonica", branch.monotonic),
                ("ciclica", branch.ciclica),
            ):
                if mechanics["status"] != "converged":
                    identity = f"{sheet.sheet_name}/{branch.curve['id']}/{mode_name}"
                    if identity not in best_effort_branches:
                        best_effort_branches.append(identity)
            for warning in branch.warnings:
                stage_warnings.append(
                    StageMessage(
                        "section_warning",
                        warning,
                        {
                            "sheet_name": sheet.sheet_name,
                            "curve_id": str(branch.curve["id"]),
                        },
                    )
                )

        for mode_name in ("monotonica", "ciclica"):
            try:
                for artifact in build_section_tables(sheet, mode_name=mode_name):
                    _add_presentation_artifact(
                        artifact,
                        sheet_id=sheet_id,
                        mode_name=mode_name,
                        base_uri=base_uri,
                        request=request,
                        manifests=manifests,
                        contents=contents,
                        dependencies=result_dependencies,
                    )
            except Exception as exc:
                failure = {
                    "sheet_name": sheet.sheet_name,
                    "mode": mode_name,
                    "kind": "tables",
                    "error": str(exc),
                }
                presentation_failures.append(failure)
                stage_warnings.append(
                    StageMessage(
                        "presentation_failed",
                        f"Table presentation failed for {sheet.sheet_name}/{mode_name}: {exc}",
                        failure,
                    )
                )
            try:
                for artifact in render_section_figures(sheet, mode_name=mode_name):
                    _add_presentation_artifact(
                        artifact,
                        sheet_id=sheet_id,
                        mode_name=mode_name,
                        base_uri=base_uri,
                        request=request,
                        manifests=manifests,
                        contents=contents,
                        dependencies=result_dependencies,
                    )
            except Exception as exc:
                failure = {
                    "sheet_name": sheet.sheet_name,
                    "mode": mode_name,
                    "kind": "figures",
                    "error": str(exc),
                }
                presentation_failures.append(failure)
                stage_warnings.append(
                    StageMessage(
                        "presentation_failed",
                        f"Figure presentation failed for {sheet.sheet_name}/{mode_name}: {exc}",
                        failure,
                    )
                )

    stage_result = StageResult(
        schema_version="2",
        module_id=MODULE_ID,
        stage_number=STAGE_NUMBER,
        execution_status=ExecutionStatus.COMPLETED,
        numerical_quality=(
            NumericalQualityStatus.BEST_EFFORT
            if best_effort_branches
            else NumericalQualityStatus.CONVERGED
        ),
        applicability=ApplicabilityStatus.APPLICABLE,
        performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
        artifacts=tuple(manifests),
        warnings=tuple(stage_warnings),
        metadata={
            "source_type": "external_moment_curvature",
            "sheet_count": result.sheet_count,
            "curve_count": result.curve_count,
            "best_effort_branches": best_effort_branches,
            "ciclica_response_semantics": "truncated_or_reused_monotonic_backbone",
            "ciclica_is_hysteretic": False,
            "presentation_status": (
                "complete" if not presentation_failures else "incomplete"
            ),
            "presentation_failures": presentation_failures,
            "incomplete": bool(presentation_failures),
        },
    )
    return HandlerOutput(stage_result, contents)


__all__ = ["execute_section_component_characterization"]

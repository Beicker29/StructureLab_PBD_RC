"""V2 handler boundary for the existing normative hazard spectra capability."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ArtifactDependency,
    ArtifactManifest,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    ProjectSpec,
    StageResult,
)
from structurelab_pbd_rc.core.exceptions import ContractError
from structurelab_pbd_rc.io.memory_artifacts import (
    csv_rows_bytes,
    etabs_spectrum_bytes,
    xlsx_rows_bytes,
)
from structurelab_pbd_rc.services.hazard_spectra import (
    HazardSpectraInput,
    compute_hazard_spectra,
)
from structurelab_pbd_rc.workflow.registry import HandlerOutput, StageExecutionRequest


MODULE_ID = "site_hazard"
STAGE_NUMBER = "01"


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")


def _resolved_project(context_configuration: Mapping[str, Any]) -> ProjectSpec:
    raw = context_configuration.get("project_spec", context_configuration)
    if not isinstance(raw, Mapping):
        raise ContractError("RunContext project_spec must be a mapping.")
    return ProjectSpec.from_dict(dict(raw))


def _hazard_configuration(context_configuration: Mapping[str, Any]) -> dict[str, Any]:
    module_inputs = context_configuration.get("module_inputs")
    if not isinstance(module_inputs, Mapping):
        raise ContractError("RunContext must declare module_inputs for site_hazard.")
    config = module_inputs.get(MODULE_ID)
    if not isinstance(config, Mapping):
        raise ContractError("RunContext has no structured site_hazard input.")
    return dict(config)


def _input_hash(request: StageExecutionRequest, name: str) -> str:
    all_hashes = request.context.metadata.get("input_hashes", {})
    if not isinstance(all_hashes, Mapping):
        raise ContractError("RunContext input_hashes metadata is missing.")
    module_hashes = all_hashes.get(MODULE_ID, {})
    if not isinstance(module_hashes, Mapping):
        raise ContractError("RunContext site_hazard input hashes are missing.")
    value = module_hashes.get(name)
    if not isinstance(value, str):
        raise ContractError(f"RunContext has no hash for {name!r}.")
    return value


def _manifest(
    *,
    artifact_id: str,
    artifact_type: str,
    uri: str,
    content: bytes,
    request: StageExecutionRequest,
    dependencies: tuple[ArtifactDependency, ...],
    metadata: dict[str, Any] | None = None,
) -> ArtifactManifest:
    return ArtifactManifest(
        schema_version="2",
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        module_id=MODULE_ID,
        stage_number=STAGE_NUMBER,
        producer="structurelab_pbd_rc.workflow.stages.site_hazard",
        uri=uri,
        sha256=hashlib.sha256(content).hexdigest(),
        units={"period": "s", "spectral_acceleration": "g"},
        sign_conventions={"spectral_acceleration": "unsigned_nonnegative"},
        axes={"reference_system": "scalar"},
        dependencies=dependencies,
        metadata=metadata or {},
        provenance=request.expected_provenance,
    )


def execute_site_hazard(request: StageExecutionRequest) -> HandlerOutput:
    """Compute and serialize existing spectra without using CLI or repository paths."""

    if request.module.module_id != MODULE_ID:
        raise ContractError("site_hazard handler received another module identity.")
    if request.expected_provenance is None:
        raise ContractError("site_hazard requires complete V2 provenance evidence.")
    project_result = request.dependency_results.get("project_objectives")
    if project_result is None or not project_result.completed or not project_result.artifacts:
        raise ContractError("site_hazard requires a completed ProjectSpec artifact.")
    project = _resolved_project(request.context.resolved_configuration)
    config = _hazard_configuration(request.context.resolved_configuration)
    input_hash = _input_hash(request, "hazard_configuration")
    references = tuple(
        item
        for item in project.references
        if item.module_id == MODULE_ID and item.kind in {"configuration", "input"}
    )
    if not references:
        raise ContractError("ProjectSpec has no site_hazard configuration reference.")
    if not any(item.sha256 == input_hash for item in references):
        raise ContractError(
            "ProjectSpec site_hazard reference does not match the resolved input hash."
        )

    result = compute_hazard_spectra(HazardSpectraInput.from_stage_01_mapping(config))
    rows = list(result.spectrum_rows)
    parameters = list(result.parameter_rows)
    case_id = result.case_id
    base_uri = f"01_site_hazard/data/{case_id}"
    project_dependencies = tuple(
        ArtifactDependency(item.artifact_id, item.content_hash)
        for item in project_result.artifacts
    )
    contents: dict[str, bytes] = {}
    manifests: list[ArtifactManifest] = []

    input_uri = f"{base_uri}/{case_id}_input.json"
    input_content = _json_bytes(config)
    input_manifest = _manifest(
        artifact_id=f"{case_id}_input",
        artifact_type="hazard_configuration",
        uri=input_uri,
        content=input_content,
        request=request,
        dependencies=project_dependencies,
        metadata={"source_input_sha256": input_hash},
    )
    contents[input_uri] = input_content
    manifests.append(input_manifest)
    derived_dependencies = (
        *project_dependencies,
        ArtifactDependency(input_manifest.artifact_id, input_manifest.content_hash),
    )

    result_uri = f"{base_uri}/{case_id}_result.json"
    result_content = _json_bytes(result.to_dict())
    manifests.append(
        _manifest(
            artifact_id=f"{case_id}_result",
            artifact_type="hazard_service_result",
            uri=result_uri,
            content=result_content,
            request=request,
            dependencies=derived_dependencies,
            metadata=dict(result.source_metadata),
        )
    )
    contents[result_uri] = result_content

    table_specs = (
        ("spectra", rows, f"{case_id}_spectra"),
        ("parameters", parameters, f"{case_id}_parameters"),
    )
    for table_name, table_rows, filename in table_specs:
        csv_uri = f"{base_uri}/{filename}.csv"
        xlsx_uri = f"{base_uri}/{filename}.xlsx"
        csv_content = csv_rows_bytes(table_rows)
        sheet_name = (
            f"case_{'01' if case_id == 'case_01_nsr10' else '02'}_{table_name}"
        )
        xlsx_content = xlsx_rows_bytes(table_rows, sheet_name=sheet_name)
        for extension, uri, content in (
            ("csv", csv_uri, csv_content),
            ("xlsx", xlsx_uri, xlsx_content),
        ):
            manifests.append(
                _manifest(
                    artifact_id=f"{case_id}_{table_name}_{extension}",
                    artifact_type=f"hazard_{table_name}_table",
                    uri=uri,
                    content=content,
                    request=request,
                    dependencies=derived_dependencies,
                    metadata={"format": extension, "row_count": len(table_rows)},
                )
            )
            contents[uri] = content

    filename_parts = {
        "service": "service_31",
        "design": "design_475",
        "maximum_considered": "maximum_considered_2500",
    }
    for level_id in ("service", "design", "maximum_considered"):
        uri = (
            f"{base_uri}/etabs/{case_id}_{filename_parts[level_id]}_etabs_v22.txt"
        )
        content = etabs_spectrum_bytes(
            rows,
            period_key="period_s",
            value_key=result.level_columns[level_id],
        )
        manifests.append(
            _manifest(
                artifact_id=f"{case_id}_{level_id}_etabs",
                artifact_type="etabs_response_spectrum",
                uri=uri,
                content=content,
                request=request,
                dependencies=derived_dependencies,
                metadata={
                    "format": "etabs_v22_period_value",
                    "decimal_places": 8,
                    "header_lines": 0,
                    "return_period_years": {
                        "service": 31,
                        "design": 475,
                        "maximum_considered": 2500,
                    }[level_id],
                },
            )
        )
        contents[uri] = content

    stage_result = StageResult(
        schema_version="2",
        module_id=MODULE_ID,
        stage_number=STAGE_NUMBER,
        execution_status=ExecutionStatus.COMPLETED,
        numerical_quality=NumericalQualityStatus.CONVERGED,
        applicability=ApplicabilityStatus.APPLICABLE,
        performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
        artifacts=tuple(manifests),
        metadata={
            "case_id": case_id,
            "rows_count": len(rows),
            "source_type": result.source_metadata["source_type"],
            "probabilistic_hazard_result": False,
        },
    )
    return HandlerOutput(stage_result, contents)

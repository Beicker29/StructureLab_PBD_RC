"""V2-012 RunContext, ArtifactManifest, and StageResult tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ArtifactDependency,
    ArtifactManifest,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    StageMessage,
    StageResult,
    validate_artifact_dependencies,
)
from structurelab_pbd_rc.core.exceptions import ContractError, DependencyError, SchemaVersionError
from structurelab_pbd_rc.workflow.context import RunContext


def artifact(
    artifact_id: str = "project_spec",
    sha256: str = "a" * 64,
    dependencies: tuple[ArtifactDependency, ...] = (),
) -> ArtifactManifest:
    return ArtifactManifest(
        schema_version="2",
        artifact_id=artifact_id,
        artifact_type="project_spec",
        module_id="project_objectives",
        stage_number="00",
        producer="structurelab_pbd_rc.workflow.stages.project_objectives",
        uri=f"00_project_objectives/data/{artifact_id}.json",
        sha256=sha256,
        units={"length": "m", "force": "kN"},
        sign_conventions={},
        axes={"vertical": "+Z"},
        dependencies=dependencies,
    )


def test_run_context_round_trip(tmp_path: Path) -> None:
    context = RunContext(
        schema_version="2",
        run_id="run_001",
        project_id="tower_a",
        design_revision="rev_01",
        case_id="case_01",
        project_root=str(tmp_path.resolve()),
        code_version="0.1.0",
        environment={"python": "3.12"},
        resolved_configuration={"modules": ["project_objectives"]},
    )
    assert RunContext.from_json(context.to_json()) == context


def test_all_v2_012_contracts_reject_incompatible_schema(tmp_path: Path) -> None:
    context = RunContext(
        schema_version="2",
        run_id="run_001",
        project_id="tower_a",
        design_revision="rev_01",
        case_id="case_01",
        project_root=str(tmp_path.resolve()),
        code_version="0.1.0",
        environment={},
        resolved_configuration={},
    )
    for contract_type, data in (
        (RunContext, context.to_dict()),
        (ArtifactManifest, artifact().to_dict()),
        (StageResult, stage_result().to_dict()),
    ):
        data["schema_version"] = "3"
        with pytest.raises(SchemaVersionError):
            contract_type.from_dict(data)


def test_artifact_manifest_round_trip_and_module_identity() -> None:
    manifest = artifact()
    assert ArtifactManifest.from_json(manifest.to_json()) == manifest
    with pytest.raises(ContractError, match="requires stage_number"):
        replace(manifest, stage_number="03")


def test_artifact_dependencies_require_matching_id_and_hash() -> None:
    source = artifact()
    dependent = artifact(
        artifact_id="validated_project",
        sha256="b" * 64,
        dependencies=(ArtifactDependency(source.artifact_id, source.sha256),),
    )
    validate_artifact_dependencies((source, dependent))

    with pytest.raises(DependencyError, match="missing dependency"):
        validate_artifact_dependencies((dependent,))
    wrong_hash = replace(
        dependent,
        dependencies=(ArtifactDependency(source.artifact_id, "c" * 64),),
    )
    with pytest.raises(DependencyError, match="SHA-256 mismatch"):
        validate_artifact_dependencies((source, wrong_hash))


def test_artifact_dependency_validation_rejects_duplicate_ids() -> None:
    with pytest.raises(ContractError, match="Duplicate artifact_id"):
        validate_artifact_dependencies((artifact("same"), artifact("SAME", "b" * 64)))


def stage_result() -> StageResult:
    return StageResult(
        schema_version="2",
        module_id="project_objectives",
        stage_number="00",
        execution_status=ExecutionStatus.COMPLETED,
        numerical_quality=NumericalQualityStatus.NOT_APPLICABLE,
        applicability=ApplicabilityStatus.APPLICABLE,
        performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
        artifacts=(artifact(),),
        warnings=(StageMessage("criteria_pending", "Criteria are not evaluated in Stage 00."),),
        duration_seconds=0.01,
    )


def test_stage_result_round_trip_and_orthogonal_states() -> None:
    result = stage_result()
    assert StageResult.from_json(result.to_json()) == result
    assert result.completed is True
    assert result.accepted is False
    assert result.numerical_quality is NumericalQualityStatus.NOT_APPLICABLE
    assert result.applicability is ApplicabilityStatus.APPLICABLE


def test_stage_result_rejects_acceptance_without_completion_or_applicability() -> None:
    with pytest.raises(ContractError, match="execution is not completed"):
        replace(
            stage_result(),
            execution_status=ExecutionStatus.FAILED,
            performance_acceptance=PerformanceAcceptanceStatus.ACCEPTED,
        )
    with pytest.raises(ContractError, match="requires an applicable"):
        replace(
            stage_result(),
            applicability=ApplicabilityStatus.NOT_APPLICABLE,
            performance_acceptance=PerformanceAcceptanceStatus.ACCEPTED,
        )


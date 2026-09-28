"""Minimal Stage 00 validation boundary."""

from __future__ import annotations

from structurelab_pbd_rc.contracts.project import ProjectSpec
from structurelab_pbd_rc.contracts.results import (
    ApplicabilityStatus,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    StageResult,
)


MODULE_ID = "project_objectives"
STAGE_NUMBER = "00"


def evaluate_project_objectives(project: ProjectSpec) -> StageResult:
    """Confirm a valid Stage 00 contract without applying code criteria.

    Completing Stage 00 records that the project definition is structurally
    valid. It deliberately leaves performance acceptance unevaluated.
    """

    if not isinstance(project, ProjectSpec):
        raise TypeError("project must be a ProjectSpec instance.")
    return StageResult(
        schema_version=project.schema_version,
        module_id=MODULE_ID,
        stage_number=STAGE_NUMBER,
        execution_status=ExecutionStatus.COMPLETED,
        numerical_quality=NumericalQualityStatus.NOT_APPLICABLE,
        applicability=ApplicabilityStatus.APPLICABLE,
        performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
        metadata={
            "project_id": project.project_id,
            "design_revision": project.design_revision,
            "case_id": project.case_id,
        },
    )


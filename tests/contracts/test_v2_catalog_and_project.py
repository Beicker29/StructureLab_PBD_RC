"""V2-010/011 catalog, ProjectSpec, and Stage 00 tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from structurelab_pbd_rc.contracts import (
    BaseUnits,
    HazardLevel,
    InputReference,
    PerformanceObjective,
    ProjectSpec,
    SiteInfo,
)
from structurelab_pbd_rc.core.exceptions import ContractError, DependencyError, SchemaVersionError
from structurelab_pbd_rc.workflow.catalog import (
    DEFAULT_CATALOG,
    ModuleCatalog,
    ModuleDefinition,
)
from structurelab_pbd_rc.workflow.stages import evaluate_project_objectives


ROOT = Path(__file__).resolve().parents[2]


def project_spec() -> ProjectSpec:
    return ProjectSpec(
        schema_version="2",
        project_id="tower_a",
        design_revision="rev_01",
        case_id="case_01",
        site=SiteInfo(
            site_id="bogota_site",
            name="Bogota test site",
            latitude=4.711,
            longitude=-74.0721,
        ),
        base_units=BaseUnits(length="m", force="kN", time="s"),
        performance_objectives=(
            PerformanceObjective(
                objective_id="life_safety",
                name="Life safety",
                hazard_level_ids=("design",),
                acceptance_criteria_references=("criteria_source",),
            ),
        ),
        hazard_levels=(
            HazardLevel(
                hazard_level_id="design",
                name="Design hazard",
                return_period_years=475,
                source_reference_id="hazard_config",
            ),
        ),
        references=(
            InputReference(
                reference_id="hazard_config",
                kind="configuration",
                uri="configs/v2/01_site_hazard/design.yaml",
                module_id="site_hazard",
            ),
            InputReference(
                reference_id="criteria_source",
                kind="criteria",
                uri="references/project/performance-objectives.md",
                module_id="project_objectives",
            ),
        ),
    )


def test_catalog_has_unique_stable_00_to_12_mapping() -> None:
    expected = {
        "00": "project_objectives",
        "01": "site_hazard",
        "02": "baseline_model",
        "03": "material_characterization",
        "04": "section_component_characterization",
        "05": "ground_motion",
        "06": "nonlinear_model",
        "07": "nonlinear_analysis",
        "08": "demand_performance",
        "09": "collapse_fragility",
        "10": "damage_loss",
        "11": "seismic_risk",
        "12": "reporting_iteration",
    }
    assert {item.stage_number: item.module_id for item in DEFAULT_CATALOG.modules} == expected
    assert DEFAULT_CATALOG.resolve("03").module_id == "material_characterization"
    assert DEFAULT_CATALOG.resolve("material_characterization").stage_number == "03"


def test_catalog_rejects_legacy_numeric_aliases_and_duplicate_ids() -> None:
    with pytest.raises(ContractError, match="ambiguous"):
        DEFAULT_CATALOG.resolve("stage_02")
    duplicate = ModuleDefinition("01", "project_objectives", "Duplicate ID")
    with pytest.raises(ContractError, match="Duplicate module_id"):
        ModuleCatalog((DEFAULT_CATALOG.by_number("00"), duplicate))


def test_catalog_rejects_unknown_dependency_and_incompatible_version() -> None:
    orphan = ModuleDefinition("00", "project_objectives", "Project", ("missing",))
    with pytest.raises(DependencyError, match="unknown dependency"):
        ModuleCatalog((orphan,))
    with pytest.raises(SchemaVersionError):
        ModuleCatalog((DEFAULT_CATALOG.by_number("00"),), schema_version="3")


def test_project_spec_json_round_trip_and_stage_00_does_not_accept() -> None:
    project = project_spec()
    restored = ProjectSpec.from_json(project.to_json())
    assert restored == project
    assert restored.units == restored.base_units

    result = evaluate_project_objectives(restored)
    assert result.completed is True
    assert result.accepted is False
    assert result.to_dict()["performance_acceptance"] == "not_evaluated"


def test_project_spec_rejects_duplicate_and_dangling_ids() -> None:
    data = project_spec().to_dict()
    data["hazard_levels"].append(dict(data["hazard_levels"][0], name="Duplicate"))
    with pytest.raises(ContractError, match="Duplicate hazard_level_id"):
        ProjectSpec.from_dict(data)

    data = project_spec().to_dict()
    data["performance_objectives"][0]["hazard_level_ids"] = ["unknown"]
    with pytest.raises(ContractError, match="unknown hazard levels"):
        ProjectSpec.from_dict(data)

    data = project_spec().to_dict()
    data["references"] = []
    data["performance_objectives"][0]["acceptance_criteria_references"] = []
    data["hazard_levels"][0]["source_reference_id"] = None
    with pytest.raises(ContractError, match="configuration or input reference"):
        ProjectSpec.from_dict(data)


def test_project_spec_rejects_incompatible_schema() -> None:
    data = project_spec().to_dict()
    data["schema_version"] = "1"
    with pytest.raises(SchemaVersionError):
        ProjectSpec.from_dict(data)


@pytest.mark.parametrize(
    ("fixture", "legacy_stage_id"),
    [
        ("hazard/manifest.json", "stage_01"),
        ("materials/manifest.json", "stage_02"),
        ("sections/manifest.json", "stage_03"),
    ],
)
def test_v1_fixture_stage_ids_remain_legacy_and_unambiguous(
    fixture: str, legacy_stage_id: str
) -> None:
    manifest = json.loads((ROOT / "tests" / "fixtures" / "v1" / fixture).read_text("utf-8"))
    assert manifest["stage_id"] == legacy_stage_id
    with pytest.raises(ContractError, match="ambiguous"):
        DEFAULT_CATALOG.resolve(legacy_stage_id)


"""V2-017 in-memory hazard service, handler, publication, and V1 regressions."""

from __future__ import annotations

import hashlib
import json
import csv
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from structurelab_pbd_rc.contracts import (
    BaseUnits,
    HazardLevel,
    InputReference,
    PerformanceObjective,
    ProjectSpec,
    SiteInfo,
)
from structurelab_pbd_rc.io.memory_artifacts import csv_rows_bytes, etabs_spectrum_bytes
from structurelab_pbd_rc.io.read_xlsx import read_xlsx_table
from structurelab_pbd_rc.io.artifacts import TransactionalPublisher
from structurelab_pbd_rc.services import HazardSpectraInput, compute_hazard_spectra
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.registry import default_handler_registry
from structurelab_pbd_rc.workflow.reuse import PublishedRunIndex
from structurelab_pbd_rc.workflow.runner import PlanStatus, WorkflowRunner


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests/fixtures/v1/hazard"
CASES = (
    (
        "case_01_nsr10",
        ROOT / "configs/stage_01/case_01_nsr10_spectra.yaml",
        FIXTURE_ROOT / "stage_01/nsr10_spectra/data",
        {
            "service": "Sa_servicio_31",
            "design": "Sa_diseno_475",
            "maximum_considered": "Sa_maximo_considerado_2500",
        },
    ),
    (
        "case_02_sgc_ccp14",
        ROOT / "configs/stage_01/case_02_sgc_ccp14_spectra.yaml",
        FIXTURE_ROOT / "stage_01/ccp14_spectra/data",
        {
            "service": "Sa_SGC_CCP14_31",
            "design": "Sa_SGC_CCP14_475",
            "maximum_considered": "Sa_SGC_CCP14_2500",
        },
    ),
)


def load_config(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def project_spec(case_id: str, config_hash: str) -> ProjectSpec:
    return ProjectSpec(
        schema_version="2",
        project_id="hazard_regression",
        design_revision="rev_01",
        case_id=case_id,
        site=SiteInfo(site_id="canonical_site", name="Canonical V1 hazard site"),
        base_units=BaseUnits(length="m", force="kN", time="s"),
        performance_objectives=(
            PerformanceObjective(
                objective_id="spectral_characterization",
                name="Spectral characterization only",
                hazard_level_ids=("service", "design", "maximum_considered"),
            ),
        ),
        hazard_levels=(
            HazardLevel("service", "Service", return_period_years=31),
            HazardLevel("design", "Design", return_period_years=475),
            HazardLevel("maximum_considered", "Maximum", return_period_years=2500),
        ),
        references=(
            InputReference(
                reference_id="hazard_configuration",
                kind="configuration",
                uri=f"configs/stage_01/{case_id}_spectra.yaml",
                module_id="site_hazard",
                sha256=config_hash,
                schema_version="v1-stage-01",
            ),
        ),
        metadata={"scope": "normative_spectra_not_probabilistic_hazard"},
    )


def run_context(
    tmp_path: Path,
    *,
    case_id: str,
    config_path: Path,
    run_id: str,
    config: dict[str, object] | None = None,
    config_hash: str | None = None,
) -> RunContext:
    resolved_config = config or load_config(config_path)
    source_hash = config_hash or hashlib.sha256(config_path.read_bytes()).hexdigest()
    project = project_spec(case_id, source_hash)
    project_bytes = project.to_json(indent=2).encode("utf-8")
    return RunContext(
        schema_version="2",
        run_id=run_id,
        project_id=project.project_id,
        design_revision=project.design_revision,
        case_id=project.case_id,
        project_root=str(tmp_path.resolve()),
        code_version="0.1.0",
        environment={"test": "v2-017"},
        resolved_configuration={
            "project_spec": project.to_dict(),
            "module_inputs": {"site_hazard": resolved_config},
        },
        metadata={
            "input_hashes": {
                "project_objectives": {
                    "project_spec": hashlib.sha256(project_bytes).hexdigest()
                },
                "site_hazard": {"hazard_configuration": source_hash},
            }
        },
    )


def normalized_lines(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


@pytest.mark.parametrize(("case_id", "config_path", "fixture_data", "columns"), CASES)
def test_in_memory_service_matches_frozen_v1_scientific_tables(
    case_id: str,
    config_path: Path,
    fixture_data: Path,
    columns: dict[str, str],
) -> None:
    result = compute_hazard_spectra(
        HazardSpectraInput.from_stage_01_mapping(load_config(config_path))
    )
    assert result.case_id == case_id
    assert len(result.periods) == 501
    assert result.periods[0] == 0.0
    assert result.periods[-1] == 5.0
    assert dict(result.level_columns) == columns
    spectra_fixture = fixture_data / f"{case_id}_spectra.csv"
    parameters_fixture = fixture_data / f"{case_id}_parameters.csv"
    assert normalized_lines(csv_rows_bytes(result.spectrum_rows)) == normalized_lines(
        spectra_fixture.read_bytes()
    )
    assert normalized_lines(csv_rows_bytes(result.parameter_rows)) == normalized_lines(
        parameters_fixture.read_bytes()
    )
    assert result.period_boundary.unit == "s"
    assert result.acceleration_boundary.unit == "g"
    assert result.source_metadata["probabilistic_hazard_result"] is False
    fixture_manifest = json.loads(
        (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    fixture_case = next(
        item for item in fixture_manifest["cases"] if item["case_id"] == case_id
    )
    assert result.transition_parameters == fixture_case["transition_parameters"]
    assert [dict(item) for item in result.parameter_rows] == fixture_case["parameter_rows"]

    filename_parts = {
        "service": "service_31",
        "design": "design_475",
        "maximum_considered": "maximum_considered_2500",
    }
    for level_id, value_key in columns.items():
        actual = etabs_spectrum_bytes(
            result.spectrum_rows,
            period_key="period_s",
            value_key=value_key,
        )
        expected = (
            fixture_data
            / "etabs"
            / f"{case_id}_{filename_parts[level_id]}_etabs_v22.txt"
        ).read_bytes()
        assert normalized_lines(actual) == normalized_lines(expected)


@pytest.mark.parametrize(("case_id", "config_path", "fixture_data", "columns"), CASES)
def test_v2_executes_stage_00_then_site_hazard_and_publishes_all_formats(
    tmp_path: Path,
    case_id: str,
    config_path: Path,
    fixture_data: Path,
    columns: dict[str, str],
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    context = run_context(
        tmp_path,
        case_id=case_id,
        config_path=config_path,
        run_id="run_001",
    )
    runner = WorkflowRunner(publisher=publisher)
    plan = runner.plan("site_hazard", context=context)
    assert plan.execution_order == ("project_objectives", "site_hazard")
    assert plan.entry("project_objectives").status is PlanStatus.READY
    assert plan.entry("site_hazard").status is PlanStatus.READY

    outcome = runner.run(context, "site_hazard")
    assert outcome.completed
    assert [item.module_id for item in outcome.stage_results] == [
        "project_objectives",
        "site_hazard",
    ]
    hazard_result = outcome.result("site_hazard")
    assert hazard_result.accepted is False
    assert hazard_result.metadata["probabilistic_hazard_result"] is False
    final = publisher.final_path(context)
    manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    hazard_artifacts = [
        item for item in manifest["artifacts"] if item["module_id"] == "site_hazard"
    ]
    assert len(hazard_artifacts) == 9
    assert all(item["provenance"] for item in hazard_artifacts)
    assert all(item["units"]["spectral_acceleration"] == "g" for item in hazard_artifacts)
    assert all(
        item["sign_conventions"]["spectral_acceleration"] == "unsigned_nonnegative"
        for item in hazard_artifacts
    )

    for table_name in ("spectra", "parameters"):
        xlsx = final / (
            f"01_site_hazard/data/{case_id}/{case_id}_{table_name}.xlsx"
        )
        csv_fixture = fixture_data / f"{case_id}_{table_name}.csv"
        with csv_fixture.open(encoding="utf-8") as stream:
            fixture_rows = list(csv.DictReader(stream))
        xlsx_table = read_xlsx_table(xlsx)
        headers = xlsx_table[0]
        xlsx_rows = [dict(zip(headers, row)) for row in xlsx_table[1:]]
        assert headers == list(fixture_rows[0])
        assert len(xlsx_rows) == len(fixture_rows)
        for actual_row, fixture_row in zip(xlsx_rows, fixture_rows):
            for key in headers:
                left = actual_row[key]
                right = fixture_row[key]
                if isinstance(left, (int, float)):
                    assert float(left) == pytest.approx(float(right), rel=0, abs=1e-15)
                else:
                    assert str(left) == right


def test_hazard_publication_is_reused_without_recalculation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id, config_path, _, _ = CASES[0]
    publisher = TransactionalPublisher(tmp_path / "outputs")
    first_context = run_context(
        tmp_path, case_id=case_id, config_path=config_path, run_id="run_001"
    )
    WorkflowRunner(publisher=publisher).run(first_context, "site_hazard")
    reference = publisher.published_reference(first_context)
    second_context = run_context(
        tmp_path, case_id=case_id, config_path=config_path, run_id="run_002"
    )
    runner = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    )
    plan = runner.plan("site_hazard", context=second_context)
    assert plan.entry("project_objectives").status is PlanStatus.REUSABLE
    assert plan.entry("site_hazard").status is PlanStatus.REUSABLE
    monkeypatch.setattr(
        "structurelab_pbd_rc.workflow.stages.site_hazard.compute_hazard_spectra",
        lambda inputs: (_ for _ in ()).throw(AssertionError("must not recalculate")),
    )
    outcome = runner.run(second_context, "site_hazard")
    assert outcome.completed
    assert publisher.final_path(second_context).is_dir()


def test_hazard_configuration_change_invalidates_reuse(tmp_path: Path) -> None:
    case_id, config_path, _, _ = CASES[0]
    publisher = TransactionalPublisher(tmp_path / "outputs")
    first_context = run_context(
        tmp_path, case_id=case_id, config_path=config_path, run_id="run_001"
    )
    WorkflowRunner(publisher=publisher).run(first_context, "site_hazard")
    reference = publisher.published_reference(first_context)
    changed = deepcopy(load_config(config_path))
    changed["hazard"]["seismic"]["period_range"]["end"] = 4.99
    changed_hash = hashlib.sha256(
        json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    current = run_context(
        tmp_path,
        case_id=case_id,
        config_path=config_path,
        run_id="run_002",
        config=changed,
        config_hash=changed_hash,
    )
    plan = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    ).plan("site_hazard", context=current)
    assert plan.entry("project_objectives").status is PlanStatus.INVALIDATED
    assert plan.entry("site_hazard").status is PlanStatus.INVALIDATED


def test_v2_hazard_run_does_not_modify_frozen_v1_outputs(tmp_path: Path) -> None:
    v1_root = ROOT / "outputs/stage_01"
    before = {
        path.relative_to(v1_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in v1_root.rglob("*")
        if path.is_file()
    }
    case_id, config_path, _, _ = CASES[1]
    context = run_context(
        tmp_path, case_id=case_id, config_path=config_path, run_id="run_001"
    )
    WorkflowRunner(
        publisher=TransactionalPublisher(tmp_path / "isolated_outputs")
    ).run(context, "site_hazard")
    after = {
        path.relative_to(v1_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in v1_root.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_default_registry_marks_site_hazard_implemented() -> None:
    registry = default_handler_registry()
    assert registry.module_ids() == (
        "material_characterization",
        "project_objectives",
        "section_component_characterization",
        "site_hazard",
    )
    plan = WorkflowRunner(registry=registry).plan("site_hazard")
    assert plan.entry("project_objectives").status is PlanStatus.READY
    assert plan.entry("site_hazard").status is PlanStatus.READY

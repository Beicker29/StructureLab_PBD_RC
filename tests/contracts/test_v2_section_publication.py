"""V2-021 section handler, presentation, publication, and reuse tests."""

from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest
import yaml

from structurelab_pbd_rc.contracts import (
    BaseUnits,
    HazardLevel,
    InputReference,
    NumericalQualityStatus,
    PerformanceObjective,
    ProjectSpec,
    SiteInfo,
)
from structurelab_pbd_rc.io.artifacts import TransactionalPublisher
from structurelab_pbd_rc.io.read_xlsx import list_xlsx_sheets, read_xlsx_rows
from structurelab_pbd_rc.presentation.section_characterization import (
    build_section_tables,
    render_section_figures,
)
from structurelab_pbd_rc.services import (
    SectionCharacterizationInput,
    SectionCharacterizationService,
    SectionWorksheetInput,
)
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.registry import default_handler_registry
from structurelab_pbd_rc.workflow.reuse import PublishedRunIndex
from structurelab_pbd_rc.workflow.runner import PlanStatus, WorkflowRunner


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/stage_03/section_characterization.yaml"
FIXTURE_ROOT = ROOT / "tests/fixtures/v1/sections"
V1_OUTPUT_ROOT = ROOT / "outputs/stage_03"
MODULE_ID = "section_component_characterization"
IMPLEMENTATION_VERSION = (
    "moment-curvature-kernel-v1+service-v2-020+publication-v2-021.1"
)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def section_configuration() -> dict[str, Any]:
    service_config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    workbook = ROOT / str(service_config["source"]["workbook"])
    worksheets = [
        {
            "sheet_name": sheet_name,
            "rows": read_xlsx_rows(workbook, sheet_name=sheet_name),
        }
        for sheet_name in list_xlsx_sheets(workbook)
    ]
    return {
        "schema_version": "2",
        "service_config": service_config,
        "worksheets": worksheets,
        "source_metadata": {
            "source_type": "external_xlsx_moment_curvature",
            "configuration_sha256": hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
            "workbook_sha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
            "fixture": "V2-006",
        },
    }


def project_spec(config_hash: str) -> ProjectSpec:
    return ProjectSpec(
        schema_version="2",
        project_id="sections_regression",
        design_revision="rev_01",
        case_id="canonical_m_phi",
        site=SiteInfo(site_id="canonical_site", name="Canonical section test site"),
        base_units=BaseUnits(length="m", force="kN", time="s"),
        performance_objectives=(
            PerformanceObjective(
                objective_id="section_characterization_only",
                name="Imported section characterization only",
                hazard_level_ids=("reference",),
            ),
        ),
        hazard_levels=(HazardLevel("reference", "Reference level"),),
        references=(
            InputReference(
                reference_id="section_configuration",
                kind="configuration",
                uri="configs/v2/04_section_component_characterization/canonical.json",
                module_id=MODULE_ID,
                sha256=config_hash,
                schema_version="2",
            ),
        ),
        metadata={"scope": "canonical_v1_section_regression"},
    )


def run_context(
    tmp_path: Path,
    *,
    run_id: str,
    config: dict[str, Any] | None = None,
    declared_hash: str | None = None,
) -> RunContext:
    resolved = config or section_configuration()
    config_hash = hashlib.sha256(_json_bytes(resolved)).hexdigest()
    project = project_spec(config_hash)
    project_hash = hashlib.sha256(project.to_json(indent=2).encode("utf-8")).hexdigest()
    return RunContext(
        schema_version="2",
        run_id=run_id,
        project_id=project.project_id,
        design_revision=project.design_revision,
        case_id=project.case_id,
        project_root=str(tmp_path.resolve()),
        code_version="0.1.0",
        environment={"test": "v2-021"},
        resolved_configuration={
            "project_spec": project.to_dict(),
            "module_inputs": {MODULE_ID: resolved},
        },
        metadata={
            "input_hashes": {
                "project_objectives": {"project_spec": project_hash},
                MODULE_ID: {
                    "section_configuration": declared_hash or config_hash,
                },
            }
        },
    )


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _scientific_results(final: Path) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for path in (final / "04_section_component_characterization").rglob(
        "scientific_result.json"
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        values[payload["sheet_name"]] = payload
    return values


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _assert_published_rows_equal_fixture(
    published_path: Path,
    fixture_path: Path,
) -> None:
    actual = _csv_rows(published_path)
    expected = _csv_rows(fixture_path)
    assert actual == expected, (published_path, fixture_path)


def test_workflow_plan_marks_section_characterization_ready() -> None:
    registry = default_handler_registry()
    plan = WorkflowRunner(registry=registry).plan(MODULE_ID)

    assert registry.has(MODULE_ID)
    assert plan.execution_order == ("project_objectives", MODULE_ID)
    assert plan.entry("project_objectives").status is PlanStatus.READY
    assert plan.entry(MODULE_ID).status is PlanStatus.READY
    assert plan.entry(MODULE_ID).required_dependencies == ("project_objectives",)


def test_v2_runner_publishes_ten_equivalent_sheets_tables_and_figures(
    tmp_path: Path,
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    context = run_context(tmp_path, run_id="run_001")
    outcome = WorkflowRunner(publisher=publisher).run(context, MODULE_ID)

    assert outcome.completed
    assert outcome.execution_order == ("project_objectives", MODULE_ID)
    stage = outcome.result(MODULE_ID)
    assert stage.completed
    assert stage.accepted is False
    assert stage.performance_acceptance.value == "not_evaluated"
    assert stage.numerical_quality is NumericalQualityStatus.BEST_EFFORT
    assert stage.metadata["sheet_count"] == 10
    assert stage.metadata["curve_count"] == 20
    assert stage.metadata["presentation_status"] == "complete"
    assert stage.metadata["ciclica_is_hysteretic"] is False
    assert stage.metadata["ciclica_response_semantics"] == (
        "truncated_or_reused_monotonic_backbone"
    )
    assert len(stage.artifacts) == 221
    assert all(artifact.provenance is not None for artifact in stage.artifacts)
    assert {
        artifact.provenance.implementation_version
        for artifact in stage.artifacts
        if artifact.provenance is not None
    } == {IMPLEMENTATION_VERSION}
    assert all(
        artifact.provenance is not None
        and artifact.provenance.backend_version.startswith("matplotlib-")
        and artifact.provenance.input_hashes["section_configuration"]
        for artifact in stage.artifacts
    )

    final = publisher.final_path(context)
    assert final == (
        tmp_path
        / "outputs/v2/sections_regression/rev_01/canonical_m_phi/run_001"
    ).resolve()
    assert not list((tmp_path / "outputs/v2/.tmp").glob("*"))
    scientific = _scientific_results(final)
    fixture_manifest = json.loads(
        (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    assert list(scientific) == fixture_manifest["processed_sheet_order"]

    for index, expected_sheet in enumerate(fixture_manifest["sheets"], start=1):
        payload = scientific[expected_sheet["sheet_name"]]
        assert payload["warnings"] == expected_sheet["warnings"]
        assert payload["modes"]["monotonica"]["parameter_rows"] == expected_sheet[
            "modes"
        ]["monotonica"]["parameters"]
        assert payload["modes"]["ciclica"]["parameter_rows"] == expected_sheet[
            "modes"
        ]["ciclica"]["parameters"]
        assert payload["modes"]["ciclica"]["is_hysteretic"] is False
        assert payload["modes"]["ciclica"]["response_semantics"] == (
            "truncated_or_reused_monotonic_backbone"
        )
        fixture_sheet = (
            FIXTURE_ROOT / "stage_03" / expected_sheet["output_folder"]
        )
        published_sheet = (
            final
            / "04_section_component_characterization/imported_m_phi"
            / f"sheet_{index:02d}"
        )
        for mode_name in ("monotonica", "ciclica"):
            fixture_data = fixture_sheet / mode_name / "data"
            tables = published_sheet / mode_name / "tables"
            _assert_published_rows_equal_fixture(
                tables / "moment_curvature.csv",
                fixture_data / "moment_curvature_curves.csv",
            )
            _assert_published_rows_equal_fixture(
                tables / "bilinear_curves.csv",
                fixture_data / "bilinear_curves.csv",
            )
            _assert_published_rows_equal_fixture(
                tables / "parameters.csv",
                fixture_data / "bilinearization_parameters.csv",
            )
            assert (tables / "moment_curvature.xlsx").is_file()
            assert (tables / "bilinear_curves.xlsx").is_file()
            assert (tables / "parameters.xlsx").is_file()
            figures = published_sheet / mode_name / "figures"
            assert len(list(figures.glob("*.png"))) == 3
            assert all(path.read_bytes().startswith(b"\x89PNG") for path in figures.glob("*.png"))
        _assert_published_rows_equal_fixture(
            published_sheet / "ciclica/tables/cut_points.csv",
            fixture_sheet / "ciclica/data/cyclic_cut_points.csv",
        )
    assert not list(final.rglob("*.pdf"))
    assert not list(final.rglob("*.html"))


def test_presentation_consumes_structured_results_without_mutation() -> None:
    config = section_configuration()
    worksheet = config["worksheets"][0]
    request = SectionCharacterizationInput.from_resolved_inputs(
        config["service_config"],
        worksheets=(
            SectionWorksheetInput.from_rows(
                worksheet["sheet_name"], worksheet["rows"]
            ),
        ),
        provenance=config["source_metadata"],
    )
    sheet = SectionCharacterizationService().evaluate(request).sheets[0]
    before = json.dumps(
        {
            "monotonica": [dict(row) for row in sheet.monotonica.parameter_rows],
            "ciclica": [dict(row) for row in sheet.ciclica.parameter_rows],
        },
        sort_keys=True,
    )

    tables = build_section_tables(sheet, mode_name="ciclica")
    figures = render_section_figures(sheet, mode_name="ciclica")

    after = json.dumps(
        {
            "monotonica": [dict(row) for row in sheet.monotonica.parameter_rows],
            "ciclica": [dict(row) for row in sheet.ciclica.parameter_rows],
        },
        sort_keys=True,
    )
    assert after == before
    assert {artifact.relative_name for artifact in tables} == {
        "moment_curvature.csv",
        "moment_curvature.xlsx",
        "bilinear_curves.csv",
        "bilinear_curves.xlsx",
        "parameters.csv",
        "parameters.xlsx",
        "cut_points.csv",
        "cut_points.xlsx",
    }
    assert len(figures) == 3


def test_section_publication_is_reused_without_recalculation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    config = section_configuration()
    first = run_context(tmp_path, run_id="run_001", config=config)
    WorkflowRunner(publisher=publisher).run(first, MODULE_ID)
    reference = publisher.published_reference(first)
    second = run_context(tmp_path, run_id="run_002", config=config)
    runner = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    )
    plan = runner.plan(MODULE_ID, context=second)
    assert plan.entry("project_objectives").status is PlanStatus.REUSABLE
    assert plan.entry(MODULE_ID).status is PlanStatus.REUSABLE

    class FailingService:
        def evaluate(self, request: SectionCharacterizationInput) -> None:
            raise AssertionError("reused section results must not be recalculated")

    monkeypatch.setattr(
        "structurelab_pbd_rc.workflow.stages.section_component_characterization."
        "SECTION_CHARACTERIZATION_SERVICE",
        FailingService(),
    )
    outcome = runner.run(second, MODULE_ID)
    assert outcome.completed
    assert outcome.result(MODULE_ID).metadata["reused_from"]["run_id"] == "run_001"
    assert publisher.final_path(second).is_dir()


def test_curve_configuration_and_cut_changes_invalidate_reuse(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    original = section_configuration()
    first = run_context(tmp_path, run_id="run_001", config=original)
    WorkflowRunner(publisher=publisher).run(first, MODULE_ID)
    reference = publisher.published_reference(first)

    changed_curve = deepcopy(original)
    first_numeric = next(
        row
        for row in changed_curve["worksheets"][0]["rows"]
        if isinstance(row.get("A"), (int, float)) and row.get("A") != 0
    )
    first_numeric["A"] = float(first_numeric["A"]) + 1e-9
    changed_config = deepcopy(original)
    changed_config["service_config"]["bilinearization"]["tolerance"] = 0.0011
    changed_cut = deepcopy(original)
    changed_cut["service_config"]["cyclic_diagram"]["cut_points_by_sheet"][
        "V1 (2-3)T"
    ]["positive_bending"]["moment"] = 753.7

    runner = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    )
    for index, changed in enumerate((changed_curve, changed_config, changed_cut), start=2):
        current = run_context(tmp_path, run_id=f"run_00{index}", config=changed)
        plan = runner.plan(MODULE_ID, context=current)
        assert plan.entry(MODULE_ID).status is PlanStatus.INVALIDATED


def test_declared_hash_mismatch_fails_without_publication(tmp_path: Path) -> None:
    context = run_context(
        tmp_path,
        run_id="run_bad_hash",
        declared_hash="0" * 64,
    )
    publisher = TransactionalPublisher(tmp_path / "outputs")
    outcome = WorkflowRunner(publisher=publisher).run(context, MODULE_ID)

    result = outcome.result(MODULE_ID)
    assert result.execution_status.value == "failed"
    assert "does not match its declared input hash" in result.errors[0].message
    assert not publisher.final_path(context).exists()


def test_figure_failure_preserves_scientific_results_but_rejects_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_figures(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic section renderer failure")

    monkeypatch.setattr(
        "structurelab_pbd_rc.workflow.stages.section_component_characterization."
        "render_section_figures",
        fail_figures,
    )
    publisher = TransactionalPublisher(tmp_path / "outputs")
    config = section_configuration()
    first = run_context(tmp_path, run_id="run_001", config=config)
    outcome = WorkflowRunner(publisher=publisher).run(first, MODULE_ID)

    assert outcome.completed
    stage = outcome.result(MODULE_ID)
    assert stage.metadata["presentation_status"] == "incomplete"
    assert stage.metadata["incomplete"] is True
    assert len(stage.metadata["presentation_failures"]) == 20
    assert stage.numerical_quality is NumericalQualityStatus.BEST_EFFORT
    assert stage.accepted is False
    final = publisher.final_path(first)
    assert len(_scientific_results(final)) == 10
    assert list((final / "04_section_component_characterization").rglob("*.csv"))
    assert not list((final / "04_section_component_characterization").rglob("*.png"))

    reference = publisher.published_reference(first)
    second = run_context(tmp_path, run_id="run_002", config=config)
    plan = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    ).plan(MODULE_ID, context=second)
    assert plan.entry(MODULE_ID).status is PlanStatus.INVALIDATED
    assert plan.entry(MODULE_ID).reason_code == "qa_policy_rejected"


def test_v2_section_run_preserves_v1_and_writes_only_isolated_v2_namespace(
    tmp_path: Path,
) -> None:
    before_outputs = _tree_hashes(V1_OUTPUT_ROOT)
    before_fixtures = _tree_hashes(FIXTURE_ROOT)
    isolated_root = tmp_path / "isolated_outputs"
    context = run_context(tmp_path, run_id="run_001")

    WorkflowRunner(
        publisher=TransactionalPublisher(isolated_root)
    ).run(context, MODULE_ID)

    assert _tree_hashes(V1_OUTPUT_ROOT) == before_outputs
    assert _tree_hashes(FIXTURE_ROOT) == before_fixtures
    files = [path for path in isolated_root.rglob("*") if path.is_file()]
    assert files
    assert all(path.is_relative_to(isolated_root / "v2") for path in files)
    assert not list(isolated_root.rglob("*.pdf"))
    assert not list(isolated_root.rglob("*.html"))


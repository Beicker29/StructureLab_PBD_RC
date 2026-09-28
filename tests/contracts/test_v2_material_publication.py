"""V2-019 material handler, presentation, publication, and reuse tests."""

from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from structurelab_pbd_rc.contracts import (
    BaseUnits,
    HazardLevel,
    InputReference,
    PerformanceObjective,
    ProjectSpec,
    SiteInfo,
)
from structurelab_pbd_rc.design.stages.stage_02_input_config import (
    load_enabled_stage_02_inputs,
)
from structurelab_pbd_rc.io.artifacts import TransactionalPublisher
from structurelab_pbd_rc.presentation.material_characterization import (
    build_material_tables,
    render_material_figures,
)
from structurelab_pbd_rc.services import MaterialEvaluationInput, MaterialEvaluationService
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.registry import default_handler_registry
from structurelab_pbd_rc.workflow.reuse import PublishedRunIndex
from structurelab_pbd_rc.workflow.runner import PlanStatus, WorkflowRunner


ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = ROOT / "configs/stage_02"
FIXTURE_ROOT = ROOT / "tests/fixtures/v1/materials"
CASE_ID = "COL75X75FC28MPa"
MODEL_IDS = {"Mon_Mander1988", "Mon_RDM2019", "Mon_MRO", "Cyc_MP"}


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def material_configuration() -> dict[str, Any]:
    models = []
    for item in load_enabled_stage_02_inputs(CONFIG_ROOT):
        models.append(
            {
                "title": item.title,
                "parameter_set_id": f"{item.model_id}_parameters",
                "material_instance_id": f"{item.model_id}_instance",
                "resolved_inputs": item.resolved_inputs,
            }
        )
    return {
        "schema_version": "2",
        "material_set_id": "canonical_v1_materials",
        "models": models,
    }


def project_spec(config_hash: str) -> ProjectSpec:
    return ProjectSpec(
        schema_version="2",
        project_id="materials_regression",
        design_revision="rev_01",
        case_id=CASE_ID,
        site=SiteInfo(site_id="canonical_site", name="Canonical material test site"),
        base_units=BaseUnits(length="m", force="kN", time="s"),
        performance_objectives=(
            PerformanceObjective(
                objective_id="material_characterization_only",
                name="Material characterization only",
                hazard_level_ids=("reference",),
            ),
        ),
        hazard_levels=(HazardLevel("reference", "Reference level"),),
        references=(
            InputReference(
                reference_id="material_configuration",
                kind="configuration",
                uri="configs/v2/03_material_characterization/canonical.json",
                module_id="material_characterization",
                sha256=config_hash,
                schema_version="2",
            ),
        ),
        metadata={"scope": "canonical_v1_material_regression"},
    )


def run_context(
    tmp_path: Path,
    *,
    run_id: str,
    config: dict[str, Any] | None = None,
) -> RunContext:
    resolved = config or material_configuration()
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
        environment={"test": "v2-019"},
        resolved_configuration={
            "project_spec": project.to_dict(),
            "module_inputs": {"material_characterization": resolved},
        },
        metadata={
            "input_hashes": {
                "project_objectives": {"project_spec": project_hash},
                "material_characterization": {
                    "material_configuration": config_hash
                },
            }
        },
    )


def _typed_curve(path: Path) -> list[dict[str, Any]]:
    string_fields = {
        "case_id",
        "branch",
        "loading_direction",
        "stress_state",
        "buckling_restraint_case",
        "compression_policy",
        "source",
        "calibration_status",
        "source_location",
        "warnings",
    }
    boolean_fields = {"reversal", "in_domain", "failed"}
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        for raw in csv.DictReader(stream):
            row: dict[str, Any] = {}
            for key, value in raw.items():
                if key in string_fields:
                    row[key] = value
                elif key in boolean_fields:
                    row[key] = value == "True"
                elif key == "step":
                    row[key] = int(value)
                else:
                    row[key] = "" if value == "" else float(value)
            rows.append(row)
    return rows


def _fixture_curve(model_id: str) -> list[dict[str, Any]]:
    path = next(
        path
        for path in (FIXTURE_ROOT / "stage_02").rglob("curve.csv")
        if path.parent.parent.name == model_id
    )
    return _typed_curve(path)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    } if root.exists() else {}


def _scientific_results(final: Path) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for path in (final / "03_material_characterization").rglob(
        "scientific_result.json"
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        values[payload["formulation"]["model_id"]] = payload
    return values


def test_workflow_plan_marks_material_characterization_ready() -> None:
    registry = default_handler_registry()
    plan = WorkflowRunner(registry=registry).plan("material_characterization")

    assert registry.module_ids() == (
        "material_characterization",
        "project_objectives",
        "section_component_characterization",
        "site_hazard",
    )
    assert plan.execution_order == (
        "project_objectives",
        "material_characterization",
    )
    assert plan.entry("project_objectives").status is PlanStatus.READY
    assert plan.entry("material_characterization").status is PlanStatus.READY
    assert plan.entry("material_characterization").required_dependencies == (
        "project_objectives",
    )


def test_v2_runner_publishes_four_equivalent_materials_and_presentations(
    tmp_path: Path,
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    context = run_context(tmp_path, run_id="run_001")

    outcome = WorkflowRunner(publisher=publisher).run(
        context,
        "material_characterization",
    )

    assert outcome.completed
    assert outcome.execution_order == (
        "project_objectives",
        "material_characterization",
    )
    stage = outcome.result("material_characterization")
    assert stage.completed
    assert stage.accepted is False
    assert stage.metadata["presentation_status"] == "complete"
    assert stage.metadata["model_count"] == 4
    assert set(stage.metadata["model_ids"]) == MODEL_IDS
    assert len(stage.artifacts) == 36
    assert all(artifact.provenance is not None for artifact in stage.artifacts)
    assert {
        artifact.provenance.implementation_version
        for artifact in stage.artifacts
        if artifact.provenance is not None
    } == {"material-kernels-v1+service-v2-018+publication-v2-019.1"}
    assert all(
        artifact.provenance is not None
        and artifact.provenance.backend_version.startswith("matplotlib-")
        and artifact.provenance.input_hashes["material_configuration"]
        for artifact in stage.artifacts
    )

    final = publisher.final_path(context)
    assert final == (
        tmp_path
        / "outputs/v2/materials_regression/rev_01/COL75X75FC28MPa/run_001"
    ).resolve()
    assert not list((tmp_path / "outputs/v2/.tmp").glob("*"))
    scientific = _scientific_results(final)
    assert set(scientific) == MODEL_IDS
    fixture_manifest = json.loads(
        (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    for model_id, payload in scientific.items():
        expected = next(
            item for item in fixture_manifest["models"] if item["model_id"] == model_id
        )
        assert payload["curve"] == _fixture_curve(model_id)
        assert payload["metrics"] == expected["metrics"]
        assert payload["warnings"] == expected["warnings"]
        assert payload["notable_points"] == expected["notable_points"]
        assert payload["calibration_status"] == expected["metadata"]["provenance"][
            "calibration_status"
        ]
        model_root = next(
            path.parent.parent
            for path in (final / "03_material_characterization").rglob(
                "data/scientific_result.json"
            )
            if json.loads(path.read_text(encoding="utf-8"))["formulation"][
                "model_id"
            ] == model_id
        )
        assert (model_root / "tables/curve.csv").is_file()
        assert (model_root / "tables/curve.xlsx").is_file()
        assert (model_root / "figures/response.png").read_bytes().startswith(b"\x89PNG")

    assert scientific["Mon_MRO"]["idealization"]["parameters"][
        "f_y_effective"
    ] == pytest.approx(518.4452190438088)
    assert scientific["Cyc_MP"]["calibration_status"] == (
        "synthetic_algorithm_verification_only"
    )
    assert scientific["Mon_Mander1988"]["boundaries"]["stress"][
        "sign_convention"
    ] == "compression_positive_tension_negative"
    for model_id in ("Mon_RDM2019", "Mon_MRO", "Cyc_MP"):
        assert scientific[model_id]["boundaries"]["stress"][
            "sign_convention"
        ] == "tension_positive_compression_negative"
    assert not list(final.rglob("*.pdf"))
    assert not list(final.rglob("*.html"))


def test_material_publication_is_reused_without_recalculation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    first = run_context(tmp_path, run_id="run_001")
    WorkflowRunner(publisher=publisher).run(first, "material_characterization")
    reference = publisher.published_reference(first)
    second = run_context(tmp_path, run_id="run_002")
    runner = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    )
    plan = runner.plan("material_characterization", context=second)
    assert plan.entry("project_objectives").status is PlanStatus.REUSABLE
    assert plan.entry("material_characterization").status is PlanStatus.REUSABLE

    class FailingService:
        def evaluate(self, request: MaterialEvaluationInput) -> None:
            raise AssertionError("reused material results must not be recalculated")

    monkeypatch.setattr(
        "structurelab_pbd_rc.workflow.stages.material_characterization."
        "MATERIAL_EVALUATION_SERVICE",
        FailingService(),
    )
    outcome = runner.run(second, "material_characterization")
    assert outcome.completed
    assert outcome.result("material_characterization").metadata["reused_from"][
        "run_id"
    ] == "run_001"
    assert publisher.final_path(second).is_dir()


def test_parameter_change_invalidates_material_reuse(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    first = run_context(tmp_path, run_id="run_001")
    WorkflowRunner(publisher=publisher).run(first, "material_characterization")
    reference = publisher.published_reference(first)
    changed = deepcopy(material_configuration())
    mro = next(
        item
        for item in changed["models"]
        if item["resolved_inputs"]["model"] == "Mon_MRO"
    )
    mro["resolved_inputs"]["parameters"]["fu_MPa"] = 574.0
    current = run_context(tmp_path, run_id="run_002", config=changed)

    plan = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    ).plan("material_characterization", context=current)

    assert plan.entry("project_objectives").status is PlanStatus.INVALIDATED
    assert plan.entry("material_characterization").status is PlanStatus.INVALIDATED


def test_figure_failure_keeps_scientific_results_publishable_and_not_reusable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_figures(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic renderer failure")

    monkeypatch.setattr(
        "structurelab_pbd_rc.workflow.stages.material_characterization."
        "render_material_figures",
        fail_figures,
    )
    publisher = TransactionalPublisher(tmp_path / "outputs")
    first = run_context(tmp_path, run_id="run_001")
    outcome = WorkflowRunner(publisher=publisher).run(
        first,
        "material_characterization",
    )

    assert outcome.completed
    stage = outcome.result("material_characterization")
    assert stage.metadata["presentation_status"] == "incomplete"
    assert stage.metadata["incomplete"] is True
    assert len(stage.metadata["presentation_failures"]) == 4
    assert stage.numerical_quality.value == "converged"
    assert all(item.code == "presentation_failed" for item in stage.warnings)
    final = publisher.final_path(first)
    scientific = _scientific_results(final)
    assert set(scientific) == MODEL_IDS
    assert scientific["Cyc_MP"]["curve"] == _fixture_curve("Cyc_MP")
    assert list((final / "03_material_characterization").rglob("curve.csv"))
    assert not list((final / "03_material_characterization").rglob("*.png"))

    reference = publisher.published_reference(first)
    second = run_context(tmp_path, run_id="run_002")
    plan = WorkflowRunner(
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    ).plan("material_characterization", context=second)
    assert plan.entry("material_characterization").status is PlanStatus.INVALIDATED
    assert plan.entry("material_characterization").reason_code == "qa_policy_rejected"


def test_presentation_consumes_results_without_mutating_scientific_values() -> None:
    item = next(
        item
        for item in load_enabled_stage_02_inputs(CONFIG_ROOT)
        if item.model_id == "Mon_MRO"
    )
    request = MaterialEvaluationInput.from_resolved_inputs(
        item.resolved_inputs,
        parameter_set_id="Mon_MRO_parameters",
        material_instance_id="Mon_MRO_instance",
    )
    result = MaterialEvaluationService().evaluate(request)
    before = [dict(row) for row in result.curve]

    tables = build_material_tables(result)
    figures = render_material_figures(result, title=item.title)

    assert [dict(row) for row in result.curve] == before
    assert {item.relative_name for item in tables} == {
        "curve.csv",
        "curve.xlsx",
        "idealization.csv",
        "idealization.xlsx",
    }
    assert {item.relative_name for item in figures} == {
        "response.png",
        "idealization.png",
    }


def test_v2_material_run_preserves_v1_outputs_and_fixtures(tmp_path: Path) -> None:
    output_root = ROOT / "outputs/stage_02"
    before_outputs = _tree_hashes(output_root)
    before_fixtures = _tree_hashes(FIXTURE_ROOT)
    context = run_context(tmp_path, run_id="run_001")

    WorkflowRunner(
        publisher=TransactionalPublisher(tmp_path / "isolated_outputs")
    ).run(context, "material_characterization")

    assert _tree_hashes(output_root) == before_outputs
    assert _tree_hashes(FIXTURE_ROOT) == before_fixtures


def test_multiple_material_set_ids_are_rejected(tmp_path: Path) -> None:
    config = material_configuration()
    config["material_set_ids"] = ["set_a", "set_b"]
    context = run_context(tmp_path, run_id="run_001", config=config)

    outcome = WorkflowRunner(
        publisher=TransactionalPublisher(tmp_path / "outputs")
    ).run(context, "material_characterization")

    result = outcome.result("material_characterization")
    assert result.execution_status.value == "failed"
    assert "Unknown material_characterization fields" in result.errors[0].message

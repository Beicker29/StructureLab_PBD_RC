"""V2-018 in-memory material service and frozen V1 scientific regressions."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest
import yaml

from structurelab_pbd_rc.design.stages.stage_02_input_config import (
    Stage02ModelInput,
    load_enabled_stage_02_inputs,
)
from structurelab_pbd_rc.design.stages.stage_02_material_characterization import (
    run as run_stage_02,
)
from structurelab_pbd_rc.services import (
    CyclicMaterialEvaluation,
    MaterialEvaluationInput,
    MonotonicMaterialEvaluation,
    create_cyclic_session,
    evaluate_material,
)
from structurelab_pbd_rc.workflow.registry import default_handler_registry


ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = ROOT / "configs/stage_02"
FIXTURE_ROOT = ROOT / "tests/fixtures/v1/materials"
CASE_ROOT = (
    FIXTURE_ROOT
    / "stage_02/Modelos_constitutivos/COL75X75FC28MPa"
)


def _inputs() -> dict[str, Stage02ModelInput]:
    return {
        item.model_id: item
        for item in load_enabled_stage_02_inputs(CONFIG_ROOT)
    }


def _request(item: Stage02ModelInput, *, suffix: str = "canonical") -> MaterialEvaluationInput:
    return MaterialEvaluationInput.from_resolved_inputs(
        item.resolved_inputs,
        parameter_set_id=f"{item.model_id}:v1-frozen",
        material_instance_id=f"{item.case_id}:{item.model_id}:{suffix}",
    )


def _model_fixture_root(item: Stage02ModelInput) -> Path:
    return CASE_ROOT / item.material / item.analysis_type / item.model_id


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
    integer_fields = {"step"}
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        for raw in csv.DictReader(stream):
            row: dict[str, Any] = {}
            for key, value in raw.items():
                if key in string_fields:
                    row[key] = value
                elif key in boolean_fields:
                    row[key] = value == "True"
                elif key in integer_fields:
                    row[key] = int(value)
                else:
                    row[key] = "" if value == "" else float(value)
            rows.append(row)
    return rows


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.mark.parametrize(
    "model_id,expected_count,result_type",
    [
        ("Mon_Mander1988", 801, MonotonicMaterialEvaluation),
        ("Mon_RDM2019", 1203, MonotonicMaterialEvaluation),
        ("Mon_MRO", 201, MonotonicMaterialEvaluation),
        ("Cyc_MP", 241, CyclicMaterialEvaluation),
    ],
)
def test_four_models_match_frozen_v1_scientific_fixtures(
    model_id: str,
    expected_count: int,
    result_type: type[object],
) -> None:
    item = _inputs()[model_id]
    result = evaluate_material(_request(item))
    fixture = _model_fixture_root(item) / "data"
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    expected_report = next(model for model in manifest["models"] if model["model_id"] == model_id)

    assert isinstance(result, result_type)
    assert len(result.curve) == expected_count
    assert [dict(row) for row in result.curve] == _typed_curve(fixture / "curve.csv")
    assert dict(result.metrics) == yaml.safe_load(
        (fixture / "metrics.yaml").read_text(encoding="utf-8")
    )["metrics"]
    assert dict(result.calculated_parameters) == yaml.safe_load(
        (fixture / "calculated_parameters.yaml").read_text(encoding="utf-8")
    )["calculated_parameters"]
    assert [dict(point) for point in result.notable_points] == expected_report["notable_points"]
    assert list(result.warnings) == expected_report["warnings"]


def test_mro_effective_yield_is_an_idealization_result_not_a_formulation_input() -> None:
    item = _inputs()["Mon_MRO"]
    request = _request(item)
    result = evaluate_material(request)

    assert isinstance(result, MonotonicMaterialEvaluation)
    assert "fy_MPa" not in request.instance.parameter_set.values
    assert result.idealization is not None
    assert result.idealization["status"] == "converged"
    assert result.idealization["parameters"]["f_y_effective"] == pytest.approx(
        518.4452190438088
    )
    assert result.calculated_parameters["fema_bilinear_idealization"] == result.idealization


def test_mander_and_rdm_keep_native_signs_and_units() -> None:
    inputs = _inputs()
    mander_request = _request(inputs["Mon_Mander1988"])
    rdm_request = _request(inputs["Mon_RDM2019"])
    mander = evaluate_material(mander_request)
    rdm = evaluate_material(rdm_request)

    assert dict(mander_request.units) == {"length": "mm", "stress": "MPa", "strain": "mm/mm"}
    assert min(float(row["stress_mpa"]) for row in mander.curve if row["stress_state"] == "tension") < 0.0
    assert max(float(row["stress_mpa"]) for row in mander.curve if row["stress_state"] == "compression") > 0.0
    assert min(float(row["stress_mpa"]) for row in rdm.curve if row["stress_state"] == "compression") < 0.0
    assert max(float(row["stress_mpa"]) for row in rdm.curve if row["stress_state"] == "tension") > 0.0


def test_two_monotonic_evaluations_are_independent() -> None:
    item = _inputs()["Mon_RDM2019"]
    first = evaluate_material(_request(item, suffix="first"))
    second = evaluate_material(_request(item, suffix="second"))

    assert first.instance.material_instance_id != second.instance.material_instance_id
    assert [dict(row) for row in first.curve] == [dict(row) for row in second.curve]
    assert first.curve is not second.curve


def test_cyclic_sessions_have_isolated_trial_commit_revert_and_reset_state() -> None:
    item = _inputs()["Cyc_MP"]
    first = create_cyclic_session(_request(item, suffix="cyclic-a"))
    second = create_cyclic_session(_request(item, suffix="cyclic-b"))

    trial = first.set_trial_strain(0.004)
    assert first.committed_state.strain == 0.0
    assert second.committed_state.strain == 0.0
    first.commit_state()
    assert first.committed_state.strain == pytest.approx(0.004)
    assert second.committed_state.strain == 0.0

    reversed_trial = first.set_trial_strain(0.001)
    assert reversed_trial.reversal is True
    reverted = first.revert_to_last_commit()
    assert reverted.strain == pytest.approx(0.004)
    assert first.committed_state.strain == pytest.approx(0.004)
    assert first.set_trial_strain(0.001).stress_mpa == pytest.approx(
        reversed_trial.stress_mpa
    )

    reset = first.reset()
    assert reset.strain == 0.0
    assert first.committed_state.strain == 0.0
    assert trial.stress_mpa != 0.0


def test_cyclic_metadata_remains_synthetic_algorithm_verification_only() -> None:
    result = evaluate_material(_request(_inputs()["Cyc_MP"]))

    assert isinstance(result, CyclicMaterialEvaluation)
    assert result.instance.provenance["calibration_status"] == (
        "synthetic_algorithm_verification_only"
    )
    assert result.metrics["calibration_status"] == "synthetic_algorithm_verification_only"
    assert {
        row["calibration_status"] for row in result.curve
    } == {"synthetic_algorithm_verification_only"}


def test_service_evaluation_is_in_memory_and_preserves_v1_trees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _inputs()["Mon_MRO"]
    request = _request(item)
    fixture_before = _tree_hashes(FIXTURE_ROOT)
    outputs_root = ROOT / "outputs/stage_02"
    outputs_before = _tree_hashes(outputs_root)
    monkeypatch.chdir(tmp_path)
    empty_before = list(tmp_path.iterdir())

    evaluate_material(request)

    assert list(tmp_path.iterdir()) == empty_before
    assert _tree_hashes(FIXTURE_ROOT) == fixture_before
    assert _tree_hashes(outputs_root) == outputs_before


def test_v1_stage_02_publication_keeps_frozen_scientific_files(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"

    run_stage_02(CONFIG_ROOT, output_root=output_root)

    generated_case = output_root / "stage_02/Modelos_constitutivos/COL75X75FC28MPa"
    for item in _inputs().values():
        fixture_data = _model_fixture_root(item) / "data"
        generated_data = (
            generated_case / item.material / item.analysis_type / item.model_id / "data"
        )
        filenames = ["curve.csv", "metrics.yaml", "calculated_parameters.yaml"]
        if item.model_id == "Mon_MRO":
            filenames.append("fema_bilinear_idealization.csv")
        for filename in filenames:
            assert (generated_data / filename).read_bytes() == (
                fixture_data / filename
            ).read_bytes()


def test_material_characterization_service_is_registered_only_after_v2_019() -> None:
    registry = default_handler_registry()

    assert "material_characterization" in registry.module_ids()


def test_structured_identity_concepts_are_distinct() -> None:
    request = _request(_inputs()["Cyc_MP"])

    assert request.instance.formulation.model_id == "Cyc_MP"
    assert request.instance.parameter_set.parameter_set_id == "Cyc_MP:v1-frozen"
    assert request.instance.material_instance_id.endswith(":canonical")
    assert "strain_history" not in request.instance.parameter_set.values
    assert request.evaluation["strain_history"] == [
        0.0,
        0.001,
        0.004,
        0.001,
        -0.002,
        0.0,
        0.006,
        -0.004,
        0.008,
    ]

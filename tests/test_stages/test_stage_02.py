"""Integration tests for jointly processed Stage 2 model JSON inputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

import pytest
import yaml

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.design.stages.stage_02_input_config import (
    ANALYSIS_TYPES,
    MATERIALS,
    load_enabled_stage_02_inputs,
)
from structurelab_pbd_rc.design.stages.stage_02_material_characterization import run


CONFIG_ROOT = Path("configs/stage_02")
RDM_LD5 = (
    CONFIG_ROOT
    / "ductile_reinforcing_steel/monotonic/Mon_RDM2019.json"
)
MRO_DB6 = (
    CONFIG_ROOT
    / "nonductile_reinforcing_steel/monotonic/Mon_MRO.json"
)
MENEGOTTO = (
    CONFIG_ROOT
    / "nonductile_reinforcing_steel/cyclic/Cyc_MP.json"
)


def _copy_input_root(tmp_path: Path, sources: list[Path]) -> Path:
    root = tmp_path / "configs" / "stage_02"
    for material in MATERIALS:
        for analysis_type in ANALYSIS_TYPES:
            (root / material / analysis_type).mkdir(parents=True, exist_ok=True)
    for source in sources:
        relative = source.relative_to(CONFIG_ROOT)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _model_root(
    output_root: Path,
    *,
    project_id: str,
    case_id: str,
    analysis_type: str,
    material: str,
    model_id: str,
) -> Path:
    return (
        output_root
        / "stage_02"
        / project_id
        / case_id
        / material
        / analysis_type
        / model_id
    )


def test_joint_artifacts(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    result = run(CONFIG_ROOT, output_root=output_root)

    assert len(result["model_reports"]) == 4
    assert len(result["cases"]) == 1
    assert {
        path.name
        for path in (output_root / "stage_02").iterdir()
        if path.is_dir()
    } == {"Modelos_constitutivos"}

    case_root = (
        output_root
        / "stage_02/Modelos_constitutivos/COL75X75FC28MPa"
    )
    assert {path.name for path in case_root.iterdir() if path.is_dir()} == set(
        MATERIALS
    )
    for material in MATERIALS:
        assert {
            path.name
            for path in (case_root / material).iterdir()
            if path.is_dir()
        } == set(ANALYSIS_TYPES)
    model_roots = [
        path.parent
        for path in (output_root / "stage_02").rglob("data")
        if path.is_dir()
    ]
    assert len(model_roots) == 4
    for model_root in model_roots:
        assert {path.name for path in model_root.iterdir() if path.is_dir()} == {
            "data",
            "figures",
            "reports",
        }
        expected_data = {
            "resolved_inputs.json",
            "calculated_parameters.yaml",
            "metrics.yaml",
            "curve.csv",
            "curve.xlsx",
        }
        expected_figures = {
            "response.png",
            "response_notable_points.png",
        }
        if model_root.name == "Mon_MRO":
            expected_data.update(
                {
                    "fema_bilinear_idealization.csv",
                    "fema_bilinear_idealization.xlsx",
                }
            )
            expected_figures.add("response_fema_bilinear_idealization.png")
        assert {path.name for path in (model_root / "data").iterdir()} == expected_data
        assert {
            path.name for path in (model_root / "figures").iterdir()
        } == expected_figures
        assert {path.name for path in (model_root / "reports").iterdir()} == {
            "model_report.yaml",
            "model_report.pdf",
        }
        assert ZipFile(model_root / "data/curve.xlsx").testzip() is None
        if model_root.name == "Mon_MRO":
            assert (
                ZipFile(
                    model_root / "data/fema_bilinear_idealization.xlsx"
                ).testzip()
                is None
            )
        assert (model_root / "reports/model_report.pdf").read_bytes()[:4] == b"%PDF"

    rdm_root = _model_root(
        output_root,
        project_id="Modelos_constitutivos",
        case_id="COL75X75FC28MPa",
        analysis_type="monotonic",
        material="ductile_reinforcing_steel",
        model_id="Mon_RDM2019",
    )
    report = yaml.safe_load(
        (rdm_root / "reports/model_report.yaml").read_text(encoding="utf-8")
    )
    resolved = json.loads(
        (rdm_root / "data/resolved_inputs.json").read_text(encoding="utf-8")
    )
    calculated = report["calculated_parameters"]
    assert calculated["epsilon_y"] == pytest.approx(0.0021)
    assert calculated["tie_area_mm2"] == pytest.approx(126.6768697744)
    assert calculated["longitudinal_bar_inertia_mm4"] == pytest.approx(
        11976.6946519793
    )
    assert calculated["reduced_flexural_rigidity_N_mm2"] == pytest.approx(
        1227246004.3776
    )
    assert calculated["bar_normalized_stiffness_N_per_mm"] == pytest.approx(
        119544.9177615367
    )
    assert calculated["tie_stiffness_N_per_mm"] == pytest.approx(126676.8697743744)
    assert calculated["equivalent_stiffness_ratio"] == pytest.approx(
        1.0596591821
    )
    assert calculated["buckling_intervals"] == 1
    assert calculated["unsupported_length_mm"] == 100.0
    assert calculated["s_over_db"] == pytest.approx(4.4994375703)
    assert calculated["L_over_D"] == pytest.approx(4.4994375703)
    assert calculated["rb"] == pytest.approx(9.2211030515)
    assert calculated["buckling_active"] is False
    assert report["metrics"]["response_branches"] == ["compression", "tension"]
    notable_points = {point["id"]: point for point in report["notable_points"]}
    assert set(notable_points) == {
        "tension_yield",
        "tension_hardening_start",
        "tension_ultimate",
        "compression_yield",
        "compression_hardening_start",
        "compression_ultimate",
    }
    assert notable_points["tension_yield"]["stress_mpa"] == pytest.approx(420.0)
    assert resolved["project_id"] == "Modelos_constitutivos"
    assert resolved["case_id"] == "COL75X75FC28MPa"
    assert resolved["model_id"] == "Mon_RDM2019"
    raw_parameters = resolved["raw"]["inputs"]["parameters"]
    assert "epsilon_y" not in raw_parameters
    assert "buckling_intervals" not in raw_parameters

    with (rdm_root / "data/curve.csv").open(encoding="utf-8", newline="") as stream:
        curve_rows = list(csv.DictReader(stream))
    assert max(float(row["strain"]) for row in curve_rows) == pytest.approx(0.10)
    assert min(float(row["strain"]) for row in curve_rows) == pytest.approx(-0.10)

    mro_root = _model_root(
        output_root,
        project_id="Modelos_constitutivos",
        case_id="COL75X75FC28MPa",
        analysis_type="monotonic",
        material="nonductile_reinforcing_steel",
        model_id="Mon_MRO",
    )
    mro_report = yaml.safe_load(
        (mro_root / "reports/model_report.yaml").read_text(encoding="utf-8")
    )
    mro_resolved = json.loads(
        (mro_root / "data/resolved_inputs.json").read_text(encoding="utf-8")
    )
    idealization = mro_report["calculated_parameters"][
        "fema_bilinear_idealization"
    ]
    idealization_parameters = idealization["parameters"]
    assert idealization["method"] == "asce_fema_energy_equivalent_stress_strain"
    assert idealization["status"] == "converged"
    assert idealization_parameters["f_y_effective"] > 0.0
    assert 0.0 < idealization_parameters["epsilon_y_effective"] < 0.0095
    assert idealization_parameters["absolute_relative_error"] <= 0.005
    assert "fy_MPa" not in mro_resolved["raw"]["inputs"]["parameters"]
    mro_notable = {point["id"]: point for point in mro_report["notable_points"]}
    assert set(mro_notable) == {"ultimate"}
    with (
        mro_root / "data/fema_bilinear_idealization.csv"
    ).open(encoding="utf-8", newline="") as stream:
        fema_rows = list(csv.DictReader(stream))
    assert [row["point"] for row in fema_rows] == [
        "origin",
        "yield",
        "ultimate",
    ]

    mander_root = _model_root(
        output_root,
        project_id="Modelos_constitutivos",
        case_id="COL75X75FC28MPa",
        analysis_type="monotonic",
        material="confined_concrete",
        model_id="Mon_Mander1988",
    )
    mander_report = yaml.safe_load(
        (mander_root / "reports/model_report.yaml").read_text(encoding="utf-8")
    )
    mander_calculated = mander_report["calculated_parameters"]
    assert mander_calculated["section_type"] == "rectangular"
    assert mander_calculated["elastic_modulus_mpa"] == 24870.0
    assert mander_calculated["f_t_mpa"] == 3.28
    assert mander_calculated["epsilon_t"] == pytest.approx(3.28 / 24870.0)
    assert mander_calculated["f_l_mpa"] == pytest.approx(2.3859465162)
    assert mander_calculated["f_cc_mpa"] == pytest.approx(41.8354552927)
    assert mander_calculated["epsilon_cc"] == pytest.approx(0.0069412340)
    assert mander_calculated["epsilon_cu"] == pytest.approx(0.0256698799)
    with (mander_root / "data/curve.csv").open(
        encoding="utf-8",
        newline="",
    ) as stream:
        mander_rows = list(csv.DictReader(stream))
    assert max(float(row["strain"]) for row in mander_rows) == pytest.approx(
        mander_calculated["epsilon_cu"]
    )
    assert min(float(row["strain"]) for row in mander_rows) == pytest.approx(
        -mander_calculated["epsilon_t"]
    )
    assert {row["stress_state"] for row in mander_rows} == {
        "compression",
        "tension",
        "zero",
    }
    compression_rows = [
        row for row in mander_rows if row["stress_state"] == "compression"
    ]
    tension_rows = [
        row for row in mander_rows if row["stress_state"] == "tension"
    ]
    assert min(float(row["stress_mpa"]) for row in compression_rows) > 0.0
    assert max(float(row["stress_mpa"]) for row in tension_rows) < 0.0


def test_stage_replace_removes_stale_stage_02_outputs(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6, MENEGOTTO])
    output_root = tmp_path / "outputs"
    run(config_root, output_root=output_root)

    case_root = output_root / "stage_02/Modelos_constitutivos/COL75X75FC28MPa"
    stale_file = case_root / "stale.txt"
    stale_file.write_text("old", encoding="utf-8")
    stale_project = output_root / "stage_02/old_project/old_case/old.txt"
    stale_project.parent.mkdir(parents=True)
    stale_project.write_text("old", encoding="utf-8")
    unrelated = output_root / "stage_03/keep.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")

    mro_copy = (
        config_root
        / "nonductile_reinforcing_steel/monotonic/Mon_MRO.json"
    )
    mro_config = json.loads(mro_copy.read_text(encoding="utf-8"))
    mro_config["inputs"]["curve_generation"]["points"] = 21
    mro_copy.write_text(json.dumps(mro_config), encoding="utf-8")
    run(config_root, output_root=output_root)

    assert not stale_file.exists()
    assert not stale_project.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (case_root / "nonductile_reinforcing_steel/monotonic").is_dir()
    assert (case_root / "nonductile_reinforcing_steel/cyclic").is_dir()
    curve_path = (
        case_root
        / "nonductile_reinforcing_steel/monotonic/Mon_MRO/data/curve.csv"
    )
    with curve_path.open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 21


def test_disabled_json_is_validated_but_not_processed(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6, MENEGOTTO])
    disabled_path = (
        config_root
        / "nonductile_reinforcing_steel/cyclic/Cyc_MP.json"
    )
    disabled = json.loads(disabled_path.read_text(encoding="utf-8"))
    disabled["enabled"] = False
    disabled_path.write_text(json.dumps(disabled), encoding="utf-8")

    inputs = load_enabled_stage_02_inputs(config_root)
    result = run(config_root, output_root=tmp_path / "outputs")

    assert [item.model_id for item in inputs] == ["Mon_MRO"]
    assert len(result["model_reports"]) == 1
    assert not (
        tmp_path
        / "outputs/stage_02/Modelos_constitutivos/COL75X75FC28MPa/"
        "nonductile_reinforcing_steel/cyclic/Cyc_MP"
    ).exists()
    assert (
        tmp_path
        / "outputs/stage_02/Modelos_constitutivos/COL75X75FC28MPa/"
        "nonductile_reinforcing_steel/cyclic"
    ).is_dir()


def test_more_than_one_json_per_model_is_rejected(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6])
    original = (
        config_root
        / "nonductile_reinforcing_steel/monotonic/Mon_MRO.json"
    )
    duplicate = original.with_name("duplicate.json")
    shutil.copy2(original, duplicate)
    duplicate_config = json.loads(duplicate.read_text(encoding="utf-8"))
    duplicate_config["enabled"] = False
    duplicate.write_text(json.dumps(duplicate_config), encoding="utf-8")

    with pytest.raises(ConfigError, match="JSON filename stem"):
        load_enabled_stage_02_inputs(config_root)


def test_single_json_path_is_rejected() -> None:
    with pytest.raises(ConfigError, match="directory containing all model JSON"):
        load_enabled_stage_02_inputs(MRO_DB6)


def test_all_models_must_use_the_same_project_and_case(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6, MENEGOTTO])
    path = config_root / "nonductile_reinforcing_steel/cyclic/Cyc_MP.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["inputs"]["case_id"] = "another_case"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="same project_id and case_id"):
        load_enabled_stage_02_inputs(config_root)


def test_required_input_identifiers_are_enforced(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6])
    path = (
        config_root
        / "nonductile_reinforcing_steel/monotonic/Mon_MRO.json"
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    config["inputs"].pop("model_id")
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="model_id"):
        load_enabled_stage_02_inputs(config_root)


def test_rdm_rejects_derived_l_over_d_input(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [RDM_LD5])
    path = (
        config_root
        / "ductile_reinforcing_steel/monotonic/Mon_RDM2019.json"
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    config["inputs"]["parameters"]["l_over_d"] = 5.0
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="cannot receive derived values"):
        run(config_root, output_root=tmp_path / "outputs")


def test_rdm_can_disable_compression_curve(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [RDM_LD5])
    path = (
        config_root
        / "ductile_reinforcing_steel/monotonic/Mon_RDM2019.json"
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    config["inputs"]["curve_generation"]["include_compression"] = False
    path.write_text(json.dumps(config), encoding="utf-8")
    output_root = tmp_path / "outputs"

    run(config_root, output_root=output_root)

    curve = _model_root(
        output_root,
        project_id="Modelos_constitutivos",
        case_id="COL75X75FC28MPa",
        analysis_type="monotonic",
        material="ductile_reinforcing_steel",
        model_id="Mon_RDM2019",
    ) / "data/curve.csv"
    with curve.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert {row["stress_state"] for row in rows} == {"zero", "tension"}

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
    / "ductile_reinforcing_steel/monotonic/steel_compression_rdm_2019_monotonic.json"
)
MRO_DB6 = (
    CONFIG_ROOT
    / "nonductile_reinforcing_steel/monotonic/modified_ramberg_osgood.json"
)
MENEGOTTO = (
    CONFIG_ROOT
    / "nonductile_reinforcing_steel/cyclic/menegotto_pinto.json"
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
        / analysis_type
        / material
        / model_id
    )


def test_joint_artifacts(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    result = run(CONFIG_ROOT, output_root=output_root)

    assert len(result["model_reports"]) == 3
    assert len(result["cases"]) == 2
    assert {
        path.name
        for path in (output_root / "stage_02").iterdir()
        if path.is_dir()
    } == {"default", "ntc5806_validation"}

    db6_case = output_root / "stage_02/ntc5806_validation/db6_algorithm_verification"
    assert {path.name for path in db6_case.iterdir() if path.is_dir()} == {
        "monotonic",
        "cyclic",
    }
    model_roots = [
        path.parent
        for path in (output_root / "stage_02").rglob("data")
        if path.is_dir()
    ]
    assert len(model_roots) == 3
    for model_root in model_roots:
        assert {path.name for path in model_root.iterdir() if path.is_dir()} == {
            "data",
            "figures",
            "reports",
        }
        assert {path.name for path in (model_root / "data").iterdir()} == {
            "resolved_inputs.json",
            "calculated_parameters.yaml",
            "metrics.yaml",
            "curve.csv",
            "curve.xlsx",
        }
        assert {path.name for path in (model_root / "figures").iterdir()} == {
            "response.png"
        }
        assert {path.name for path in (model_root / "reports").iterdir()} == {
            "model_report.yaml",
            "model_report.pdf",
        }
        assert ZipFile(model_root / "data/curve.xlsx").testzip() is None
        assert (model_root / "reports/model_report.pdf").read_bytes()[:4] == b"%PDF"

    rdm_root = _model_root(
        output_root,
        project_id="default",
        case_id="rdm_2019_ld5",
        analysis_type="monotonic",
        material="ductile_reinforcing_steel",
        model_id="steel_compression_rdm_2019_monotonic",
    )
    report = yaml.safe_load(
        (rdm_root / "reports/model_report.yaml").read_text(encoding="utf-8")
    )
    resolved = json.loads(
        (rdm_root / "data/resolved_inputs.json").read_text(encoding="utf-8")
    )
    assert report["calculated_parameters"]["s_over_db"] == 5.0
    assert report["calculated_parameters"]["L_over_D"] == 5.0
    assert report["metrics"]["response_branches"] == ["compression", "tension"]
    assert resolved["project_id"] == "default"
    assert resolved["case_id"] == "rdm_2019_ld5"
    assert resolved["model_id"] == "steel_compression_rdm_2019_monotonic"


def test_case_replace_preserves_other_cases(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6, MENEGOTTO])
    output_root = tmp_path / "outputs"
    run(config_root, output_root=output_root)

    case_root = (
        output_root
        / "stage_02/ntc5806_validation/db6_algorithm_verification"
    )
    stale_file = case_root / "stale.txt"
    stale_file.write_text("old", encoding="utf-8")
    unrelated = output_root / "stage_02/other_project/other_case/keep.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")

    mro_copy = (
        config_root
        / "nonductile_reinforcing_steel/monotonic/modified_ramberg_osgood.json"
    )
    mro_config = json.loads(mro_copy.read_text(encoding="utf-8"))
    mro_config["inputs"]["curve_generation"]["points"] = 21
    mro_copy.write_text(json.dumps(mro_config), encoding="utf-8")
    run(config_root, output_root=output_root)

    assert not stale_file.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (case_root / "monotonic").is_dir()
    assert (case_root / "cyclic").is_dir()
    curve_path = (
        case_root
        / "monotonic/nonductile_reinforcing_steel/modified_ramberg_osgood/data/curve.csv"
    )
    with curve_path.open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 21


def test_disabled_json_is_validated_but_not_processed(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6, MENEGOTTO])
    disabled_path = (
        config_root
        / "nonductile_reinforcing_steel/cyclic/menegotto_pinto.json"
    )
    disabled = json.loads(disabled_path.read_text(encoding="utf-8"))
    disabled["enabled"] = False
    disabled_path.write_text(json.dumps(disabled), encoding="utf-8")

    inputs = load_enabled_stage_02_inputs(config_root)
    result = run(config_root, output_root=tmp_path / "outputs")

    assert [item.model_id for item in inputs] == ["modified_ramberg_osgood"]
    assert len(result["model_reports"]) == 1
    assert not (
        tmp_path
        / "outputs/stage_02/ntc5806_validation/db6_algorithm_verification/cyclic"
    ).exists()


def test_more_than_one_json_per_model_is_rejected(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6])
    original = (
        config_root
        / "nonductile_reinforcing_steel/monotonic/modified_ramberg_osgood.json"
    )
    duplicate = original.with_name("duplicate.json")
    shutil.copy2(original, duplicate)
    duplicate_config = json.loads(duplicate.read_text(encoding="utf-8"))
    duplicate_config["inputs"]["project_id"] = "another_project"
    duplicate_config["inputs"]["case_id"] = "another_case"
    duplicate.write_text(json.dumps(duplicate_config), encoding="utf-8")

    with pytest.raises(ConfigError, match="Only one JSON file"):
        load_enabled_stage_02_inputs(config_root)


def test_case_insensitive_identifier_collision_is_rejected(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6, MENEGOTTO])
    second = (
        config_root
        / "nonductile_reinforcing_steel/cyclic/menegotto_pinto.json"
    )
    config = json.loads(second.read_text(encoding="utf-8"))
    config["inputs"]["project_id"] = "NTC5806_VALIDATION"
    second.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="differs only by case"):
        load_enabled_stage_02_inputs(config_root)


def test_required_input_identifiers_are_enforced(tmp_path: Path) -> None:
    config_root = _copy_input_root(tmp_path, [MRO_DB6])
    path = (
        config_root
        / "nonductile_reinforcing_steel/monotonic/modified_ramberg_osgood.json"
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
        / "ductile_reinforcing_steel/monotonic/steel_compression_rdm_2019_monotonic.json"
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
        / "ductile_reinforcing_steel/monotonic/steel_compression_rdm_2019_monotonic.json"
    )
    config = json.loads(path.read_text(encoding="utf-8"))
    config["inputs"]["curve_generation"]["include_compression"] = False
    path.write_text(json.dumps(config), encoding="utf-8")
    output_root = tmp_path / "outputs"

    run(config_root, output_root=output_root)

    curve = _model_root(
        output_root,
        project_id="default",
        case_id="rdm_2019_ld5",
        analysis_type="monotonic",
        material="ductile_reinforcing_steel",
        model_id="steel_compression_rdm_2019_monotonic",
    ) / "data/curve.csv"
    with curve.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert {row["stress_state"] for row in rows} == {"zero", "tension"}

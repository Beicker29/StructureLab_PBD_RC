"""Characterize V1 publication failures; these assertions preserve observed behavior."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from structurelab_pbd_rc.design.stages import stage_01_hazard as hazard
from structurelab_pbd_rc.design.stages import stage_02_material_characterization as materials
from structurelab_pbd_rc.design.stages import stage_03_section_characterization as sections
from structurelab_pbd_rc.design.stages.stage_02_input_config import load_enabled_stage_02_inputs


ROOT = Path(__file__).resolve().parents[2]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(*args: object, **kwargs: object) -> None:
    raise RuntimeError("injected-v1-failure")


def _sentinels(output: Path, stage: str, active: str = "old.txt") -> tuple[Path, Path, str, str]:
    own = output / stage / active
    other = output / "other_stage" / "keep.txt"
    own.parent.mkdir(parents=True, exist_ok=True)
    other.parent.mkdir(parents=True, exist_ok=True)
    own.write_bytes(b"previous-scientific-result")
    other.write_bytes(b"other-stage-result")
    return own, other, _digest(own), _digest(other)


def _section_config(tmp_path: Path) -> Path:
    config = yaml.safe_load((ROOT / "configs/stage_03/section_characterization.yaml").read_text(encoding="utf-8"))
    config["source"]["workbook"] = str((ROOT / config["source"]["workbook"]).resolve())
    config["source"]["sheets"] = "V1 (1-2 y 3-4)T"
    path = tmp_path / "section.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_stage01_validation_failure_leaves_previous_output(tmp_path: Path) -> None:
    output = tmp_path / "out"
    active, other, active_hash, other_hash = _sentinels(output, "stage_01", "nsr10_spectra/old.txt")
    config = yaml.safe_load((ROOT / "configs/stage_01/case_01_nsr10_spectra.yaml").read_text(encoding="utf-8"))
    config["units"]["period"] = "invalid"
    source = tmp_path / "invalid.yaml"
    source.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="period unit"):
        hazard.run(source, output)
    assert _digest(active) == active_hash
    assert _digest(other) == other_hash


@pytest.mark.parametrize("point", ["before_calculation", "during_write", "after_write"])
def test_stage01_failure_erases_active_case_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str) -> None:
    output = tmp_path / "out"
    active, other, _, other_hash = _sentinels(output, "stage_01", "nsr10_spectra/old.txt")
    inactive = output / "stage_01/ccp14_spectra/keep.txt"
    inactive.parent.mkdir(parents=True)
    inactive.write_bytes(b"other-case")
    inactive_hash = _digest(inactive)
    if point == "before_calculation":
        monkeypatch.setattr(hazard, "_run_case_01", _fail)
    elif point == "during_write":
        def partial(*args: object, **kwargs: object) -> None:
            (output / "stage_01/nsr10_spectra/data/partial.csv").write_bytes(b"partial")
            _fail()
        monkeypatch.setattr(hazard, "write_stage_table_pair", partial)
    else:
        monkeypatch.setattr(hazard, "write_json_result", _fail)
    with pytest.raises(RuntimeError, match="injected"):
        hazard.run(ROOT / "configs/stage_01/case_01_nsr10_spectra.yaml", output)
    assert not active.exists()
    assert _digest(inactive) == inactive_hash
    assert _digest(other) == other_hash
    if point == "during_write":
        assert (output / "stage_01/nsr10_spectra/data/partial.csv").read_bytes() == b"partial"
    if point == "after_write":
        assert list((output / "stage_01/nsr10_spectra/data").glob("*.csv"))
        assert not (output / "stage_01/nsr10_spectra/data/stage_01_results.json").exists()


def _fake_materials(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = load_enabled_stage_02_inputs(ROOT / "configs/stage_02")
    monkeypatch.setattr(materials, "load_enabled_stage_02_inputs", lambda path: inputs[:1])
    monkeypatch.setattr(materials, "_prepare_model", lambda item: {"input": item, "summary": {}})


def test_stage02_failure_before_write_preserves_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out"
    active, other, active_hash, other_hash = _sentinels(output, "stage_02")
    monkeypatch.setattr(materials, "_prepare_model", _fail)
    with pytest.raises(RuntimeError, match="injected"):
        materials.run(ROOT / "configs/stage_02", output)
    assert _digest(active) == active_hash
    assert _digest(other) == other_hash


def test_stage02_failure_while_staging_preserves_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out"
    active, other, active_hash, other_hash = _sentinels(output, "stage_02")
    _fake_materials(monkeypatch)
    def partial(prepared: object, *, staged_case_root: Path, final_case_root: Path) -> None:
        staged_case_root.mkdir(parents=True, exist_ok=True)
        (staged_case_root / "partial.csv").write_bytes(b"partial")
        _fail()
    monkeypatch.setattr(materials, "_write_prepared_model", partial)
    with pytest.raises(RuntimeError, match="injected"):
        materials.run(ROOT / "configs/stage_02", output)
    assert _digest(active) == active_hash
    assert _digest(other) == other_hash
    assert not list(output.glob(".stage_02-*"))


def test_stage02_promotion_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out"
    active, other, active_hash, other_hash = _sentinels(output, "stage_02")
    _fake_materials(monkeypatch)
    def staged(prepared: object, *, staged_case_root: Path, final_case_root: Path) -> dict[str, object]:
        staged_case_root.mkdir(parents=True, exist_ok=True)
        (staged_case_root / "new.csv").write_bytes(b"new")
        return {"metadata": {"material": "x", "analysis_type": "monotonic"}, "model_id": "x", "generated_files": {}, "warnings": []}
    monkeypatch.setattr(materials, "_write_prepared_model", staged)
    monkeypatch.setattr(materials.shutil, "move", _fail)
    with pytest.raises(RuntimeError, match="injected"):
        materials.run(ROOT / "configs/stage_02", output)
    assert _digest(active) == active_hash
    assert _digest(other) == other_hash
    assert not list(output.glob(".stage_02-*"))
    assert not list(output.glob(".bak-stage_02-*"))


def test_stage02_failure_after_promotion_leaves_new_tree_and_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out"
    old, other, _, other_hash = _sentinels(output, "stage_02")
    staged = output / ".stage_02-test"
    staged.mkdir()
    (staged / "new.csv").write_bytes(b"new")
    original_rmtree = materials.shutil.rmtree
    def fail_backup_cleanup(path: object, *args: object, **kwargs: object) -> None:
        if Path(path).name.startswith(".bak-stage_02-"):
            _fail()
        original_rmtree(path, *args, **kwargs)
    monkeypatch.setattr(materials.shutil, "rmtree", fail_backup_cleanup)
    with pytest.raises(RuntimeError, match="injected"):
        materials._replace_stage_directory(staged, output / "stage_02")
    assert not old.exists()
    assert (output / "stage_02/new.csv").read_bytes() == b"new"
    backup = list(output.glob(".bak-stage_02-*"))
    assert len(backup) == 1
    assert (backup[0] / "old.txt").read_bytes() == b"previous-scientific-result"
    assert _digest(other) == other_hash


def test_stage03_validation_failure_preserves_output(tmp_path: Path) -> None:
    output = tmp_path / "out"
    active, other, active_hash, other_hash = _sentinels(output, "stage_03")
    config = yaml.safe_load(_section_config(tmp_path).read_text(encoding="utf-8"))
    config["units"]["moment"] = "wrong"
    source = tmp_path / "invalid.yaml"
    source.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="moment unit"):
        sections.run(source, output)
    assert _digest(active) == active_hash
    assert _digest(other) == other_hash


@pytest.mark.parametrize("point", ["before_calculation", "during_write"])
def test_stage03_failure_erases_whole_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str) -> None:
    output = tmp_path / "out"
    active, other, _, other_hash = _sentinels(output, "stage_03")
    if point == "before_calculation":
        monkeypatch.setattr(sections, "_detect_sheet_curves", _fail)
    else:
        def partial(*args: object, **kwargs: object) -> None:
            (output / "stage_03/V1 (1-2 y 3-4)T/monotonica/data/partial.csv").write_bytes(b"partial")
            _fail()
        monkeypatch.setattr(sections, "write_csv_rows", partial)
    with pytest.raises(RuntimeError, match="injected"):
        sections.run(_section_config(tmp_path), output)
    assert not active.exists()
    assert _digest(other) == other_hash
    if point == "during_write":
        assert list((output / "stage_03").rglob("partial.csv"))


def test_stage03_failure_after_sheet_write_leaves_partial_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "out"
    active, other, _, other_hash = _sentinels(output, "stage_03")
    original = sections.write_json_result
    def fail_stage_summary(payload: object, path: Path) -> Path:
        if Path(path).name == "stage_03_results.json":
            _fail()
        return original(payload, path)
    monkeypatch.setattr(sections, "write_json_result", fail_stage_summary)
    with pytest.raises(RuntimeError, match="injected"):
        sections.run(_section_config(tmp_path), output)
    assert not active.exists()
    assert list((output / "stage_03").rglob("*bilinearization_parameters.csv"))
    assert not (output / "stage_03/data/stage_03_results.json").exists()
    assert _digest(other) == other_hash

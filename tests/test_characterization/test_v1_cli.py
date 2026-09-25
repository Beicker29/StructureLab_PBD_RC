"""Characterize legacy CLI routing without writing repository outputs."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from structurelab_pbd_rc.cli import run as cli
from structurelab_pbd_rc.design.stages import stage_01_hazard, stage_02_material_characterization, stage_03_section_characterization


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
EXECUTABLES = Path(sys.executable).resolve().parent
EXECUTABLE_SUFFIX = ".exe" if os.name == "nt" else ""


def test_public_runners_have_legacy_signature_and_namespace() -> None:
    assert sorted(cli.STAGES) == ["stage_01", "stage_02", "stage_03"]
    for stage in (stage_01_hazard, stage_02_material_characterization, stage_03_section_characterization):
        parameters = inspect.signature(stage.run).parameters
        assert list(parameters) == ["config_path", "output_root"]
        assert parameters["output_root"].default == "outputs"
    assert inspect.signature(cli.main).parameters["argv"].default is None


@pytest.mark.parametrize("stage", ["01", "02", "03"])
def test_installed_entrypoint_discards_cli_arguments(tmp_path: Path, stage: str) -> None:
    executable = EXECUTABLES / f"structurelab-stage-{stage}{EXECUTABLE_SUFFIX}"
    if not executable.is_file():
        pytest.skip(f"installed console script unavailable: {executable}")
    output = tmp_path / "must_remain_absent"
    command = [str(executable), "--config", str(tmp_path / "missing-override"), "--output-root", str(output)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "missing-override" not in result.stderr
    assert f"configs{os.sep}stage_{stage}" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("stage", ["01", "02", "03"])
def test_exe_defaults(tmp_path: Path, stage: str) -> None:
    executable = EXECUTABLES / f"structurelab-stage-{stage}{EXECUTABLE_SUFFIX}"
    if not executable.is_file():
        pytest.skip(f"installed console script unavailable: {executable}")
    target = tmp_path / f"configs/stage_{stage}"
    target.mkdir(parents=True)
    if stage == "01":
        source = yaml.safe_load((ROOT / "configs/stage_01/case_01_nsr10_spectra.yaml").read_text(encoding="utf-8"))
        source["hazard"]["seismic"]["period_range"]["end"] = 0.02
        (target / "case_01_nsr10_spectra.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")
    elif stage == "02":
        from structurelab_pbd_rc.design.stages.stage_02_input_config import MATERIALS, ANALYSIS_TYPES
        for material in MATERIALS:
            for analysis in ANALYSIS_TYPES:
                (target / material / analysis).mkdir(parents=True)
        source = ROOT / "configs/stage_02/nonductile_reinforcing_steel/monotonic/Mon_MRO.json"
        (target / "nonductile_reinforcing_steel/monotonic/Mon_MRO.json").write_bytes(source.read_bytes())
    else:
        source = yaml.safe_load((ROOT / "configs/stage_03/section_characterization.yaml").read_text(encoding="utf-8"))
        source["source"]["workbook"] = str((ROOT / source["source"]["workbook"]).resolve())
        source["source"]["sheets"] = "V1 (1-2 y 3-4)T"
        source["bilinearization"]["search_points"] = 1000
        (target / "section_characterization.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")
    alternate_output = tmp_path / "override_output"
    result = subprocess.run(
        [str(executable), "--config", str(tmp_path / "missing-override.yaml"), "--output-root", str(alternate_output)],
        cwd=tmp_path, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert (tmp_path / "outputs" / f"stage_{stage}").is_dir()
    assert not alternate_output.exists()


@pytest.mark.parametrize("stage", ["01", "02", "03"])
def test_script_forwards_config_argument_from_other_cwd(tmp_path: Path, stage: str) -> None:
    output = tmp_path / "must_remain_absent"
    absent = tmp_path / "missing-override.yaml"
    command = [sys.executable, str(SCRIPTS / f"run_stage_{stage}.py"), "--config", str(absent), "--output-root", str(output)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "missing-override" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("stage", ["01", "02", "03"])
def test_python_module_forwards_config_argument_from_other_cwd(tmp_path: Path, stage: str) -> None:
    output = tmp_path / "must_remain_absent"
    absent = tmp_path / "missing-override.yaml"
    command = [sys.executable, "-m", "structurelab_pbd_rc.cli.run", f"stage_{stage}", "--config", str(absent), "--output-root", str(output)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "missing-override" in result.stderr
    assert not output.exists()


def test_cli_exit_codes_and_wrapper_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = subprocess.run([sys.executable, "-m", "structurelab_pbd_rc.cli.run", "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert "--output-root" in result.stdout
    result = subprocess.run([sys.executable, "-m", "structurelab_pbd_rc.cli.run", "invalid-stage"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 2
    calls: list[list[str] | None] = []
    monkeypatch.setattr(cli, "main", lambda args: calls.append(args) or 0)
    assert cli.main_stage_01() == cli.main_stage_02() == cli.main_stage_03() == 0
    assert calls == [["stage_01"], ["stage_02"], ["stage_03"]]


def _absolute_section_config(tmp_path: Path) -> Path:
    source = ROOT / "configs/stage_03/section_characterization.yaml"
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["source"]["workbook"] = str((ROOT / config["source"]["workbook"]).resolve())
    config["source"]["sheets"] = "V1 (1-2 y 3-4)T"
    path = tmp_path / "absolute_section.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.mark.parametrize("stage,kind", [("01", "script"), ("02", "module"), ("03", "script")])
def test_cli_absolute_config_and_output_from_foreign_cwd(tmp_path: Path, stage: str, kind: str) -> None:
    config = {
        "01": ROOT / "configs/stage_01/case_01_nsr10_spectra.yaml",
        "02": ROOT / "configs/stage_02",
        "03": _absolute_section_config(tmp_path),
    }[stage]
    output = tmp_path / "absolute_output"
    prefix = [sys.executable, str(SCRIPTS / f"run_stage_{stage}.py")] if kind == "script" else [sys.executable, "-m", "structurelab_pbd_rc.cli.run", f"stage_{stage}"]
    result = subprocess.run([*prefix, "--config", str(config), "--output-root", str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    assert (output / f"stage_{stage}").is_dir()
    assert not (tmp_path / "outputs").exists()


def test_stage03_relative_workbook_is_resolved_against_cwd(tmp_path: Path) -> None:
    output = tmp_path / "out"
    command = [sys.executable, "-m", "structurelab_pbd_rc.cli.run", "stage_03", "--config", str(ROOT / "configs/stage_03/section_characterization.yaml"), "--output-root", str(output)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "M-curvatura.xlsx" in result.stderr
    assert (output / "stage_03").is_dir()  # prepare_stage_from_config creates it before source validation


@pytest.mark.parametrize("cwd_mode", ["repository", "foreign"])
def test_stage01_relative_config_and_output_follow_process_cwd(tmp_path: Path, cwd_mode: str) -> None:
    if cwd_mode == "repository":
        cwd = ROOT
        config = "configs/stage_01/case_01_nsr10_spectra.yaml"
        output = tmp_path / "repo_relative_result"
        output_arg = str(output)
    else:
        cwd = tmp_path
        source = yaml.safe_load((ROOT / "configs/stage_01/case_01_nsr10_spectra.yaml").read_text(encoding="utf-8"))
        source["hazard"]["seismic"]["period_range"]["end"] = 0.02
        (tmp_path / "configs").mkdir()
        (tmp_path / "configs/case.yaml").write_text(yaml.safe_dump(source), encoding="utf-8")
        config = "configs/case.yaml"
        output = tmp_path / "relative_result"
        output_arg = "relative_result"
    command = [sys.executable, "-m", "structurelab_pbd_rc.cli.run", "stage_01", "--config", config, "--output-root", output_arg]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr[-2000:]
    assert (output / "stage_01/nsr10_spectra/data/stage_01_results.json").is_file()

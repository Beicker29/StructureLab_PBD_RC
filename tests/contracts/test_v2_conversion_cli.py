"""V1 conversion preview and the official V2 workflow command."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from structurelab_pbd_rc.cli.workflow import main
from structurelab_pbd_rc.compat.v1 import convert_v1_to_v2
from structurelab_pbd_rc.core.exceptions import ConfigError


ROOT = Path(__file__).resolve().parents[2]
HAZARD = ROOT / "configs/stage_01/case_01_nsr10_spectra.yaml"
MATERIALS = ROOT / "configs/stage_02"
SECTIONS = ROOT / "configs/stage_03/section_characterization.yaml"
WORKBOOK = ROOT / "references/stage_03/excel/M-curvatura.xlsx"
FIXTURES = ROOT / "tests/fixtures/v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _template(tmp_path: Path, *, hazard_case: str = "case_01_nsr10") -> Path:
    template = {
        "schema_version": "2",
        "project_id": "Modelos_constitutivos",
        "design_revision": "rev_01",
        "case_id": "COL75X75FC28MPa",
        "site": {"site_id": "canonical_site", "name": "Explicit canonical source association"},
        "base_units": {"length": "m", "force": "kN", "time": "s"},
        "hazard_levels": [
            {"hazard_level_id": name, "name": name, "return_period_years": period}
            for name, period in (("service", 31), ("design", 475), ("maximum_considered", 2500))
        ],
        "performance_objectives": [{
            "objective_id": "characterization_only", "name": "Caracterización de inputs existentes",
            "hazard_level_ids": ["service", "design", "maximum_considered"],
        }],
        "material_set_id": "canonical_v1_materials",
        "v1_bindings": {
            "site_hazard": {"case_id": hazard_case},
            "material_characterization": {
                "project_id": "Modelos_constitutivos", "case_id": "COL75X75FC28MPa",
            },
            "section_component_characterization": {
                "workbook_sha256": _sha(WORKBOOK), "confirmed_for_project_case": True,
            },
        },
    }
    path = tmp_path / "template.yaml"
    path.write_text(yaml.safe_dump(template, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _convert_args(template: Path, destination: Path) -> list[str]:
    return [
        "workflow", "convert", "--project-template", str(template),
        "--stage-01", str(HAZARD), "--stage-02", str(MATERIALS),
        "--stage-03", str(SECTIONS), "--source-root", str(ROOT),
        "--destination", str(destination),
    ]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_preview_is_read_only_and_detects_ambiguity(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    destination = tmp_path / "converted"
    before = {path: _sha(path) for path in (HAZARD, SECTIONS, WORKBOOK)}
    bundle = convert_v1_to_v2(
        template_path=template, stage_01=HAZARD, stage_02=MATERIALS,
        stage_03=SECTIONS, source_root=ROOT,
    )
    assert set(bundle.module_bytes) == {
        "site_hazard", "material_characterization", "section_component_characterization",
    }
    assert bundle.preview(destination)["status"] == "preview"
    assert main(_convert_args(template, destination)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "preview"
    assert not destination.exists()
    assert all(_sha(path) == value for path, value in before.items())
    incorrect = yaml.safe_load(template.read_text(encoding="utf-8"))
    incorrect["v1_bindings"]["site_hazard"]["case_id"] = "another_case"
    template.write_text(yaml.safe_dump(incorrect), encoding="utf-8")
    with pytest.raises(ConfigError, match="case_id differs"):
        convert_v1_to_v2(template_path=template, stage_01=HAZARD, stage_02=MATERIALS, stage_03=SECTIONS, source_root=ROOT)
    assert not destination.exists()


def test_conversion_plan_run_matches_frozen_science(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Stage 02 produces nested model paths; keep the Windows test root short.
    work = tmp_path.parent / "conversion_e2e"
    work.mkdir()
    template = _template(work)
    destination = work / "converted"
    args = _convert_args(template, destination)
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "preview"
    assert main([*args, "--write"]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["status"] == "written"
    project_file = destination / "project.yaml"
    project = yaml.safe_load(project_file.read_text(encoding="utf-8"))
    assert set(item["module_id"] for item in project["references"]) == {
        "site_hazard", "material_characterization", "section_component_characterization",
    }
    assert len(project["metadata"]["v1_conversion"]["source_records"]["material_characterization"]) == 4
    for reference in project["references"]:
        assert _sha(destination / reference["uri"]) == reference["sha256"]
    before_v1 = {path: _sha(path) for path in (HAZARD, SECTIONS, WORKBOOK)}
    before_outputs = {path: _sha(path) for path in (ROOT / "outputs").glob("stage_*/**/*.csv")}
    output_root = work / "published"
    common = [
        "--project", str(project_file), "--output-root", str(output_root),
        "--module", "site_hazard", "--module", "material_characterization",
        "--module", "section_component_characterization", "--project-id", "Modelos_constitutivos",
        "--design-revision", "rev_01", "--case-id", "COL75X75FC28MPa",
    ]
    assert main(["workflow", "plan", *common]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert {item["status"] for item in planned["plan"]["modules"]} == {"ready"}
    assert not output_root.exists()
    assert main(["workflow", "run", *common, "--run-id", "run_001"]) == 0
    run = json.loads(capsys.readouterr().out)
    final = Path(run["published_path"])
    assert final.is_dir()
    assert all(item["execution_status"] == "completed" for item in run["stages"])
    assert _rows(final / "01_site_hazard/data/case_01_nsr10/case_01_nsr10_spectra.csv") == _rows(
        FIXTURES / "hazard/stage_01/nsr10_spectra/data/case_01_nsr10_spectra.csv"
    )
    material_science = list((final / "03_material_characterization").rglob("scientific_result.json"))
    assert len(material_science) == 4
    material_fixture = json.loads((FIXTURES / "materials/manifest.json").read_text(encoding="utf-8"))
    for path in material_science:
        payload = json.loads(path.read_text(encoding="utf-8"))
        model_id = payload["formulation"]["model_id"]
        fixture = next(item for item in material_fixture["models"] if item["model_id"] == model_id)
        assert payload["metrics"] == fixture["metrics"]
        assert payload["warnings"] == fixture["warnings"]
        expected_curve = next(path for path in (FIXTURES / "materials/stage_02").rglob("curve.csv") if path.parent.parent.name == model_id)
        actual_curve = next(path for path in (final / "03_material_characterization").rglob("curve.csv") if path.parent.name == "tables" and model_id in path.parts)
        assert _rows(actual_curve) == _rows(expected_curve)
    section_fixture = json.loads((FIXTURES / "sections/manifest.json").read_text(encoding="utf-8"))
    for index, sheet in enumerate(section_fixture["sheets"], start=1):
        fixture_root = FIXTURES / "sections/stage_03" / sheet["output_folder"]
        result_root = final / "04_section_component_characterization/imported_m_phi" / f"sheet_{index:02d}"
        for mode in ("monotonica", "ciclica"):
            for actual, expected in (
                ("moment_curvature.csv", "moment_curvature_curves.csv"),
                ("bilinear_curves.csv", "bilinear_curves.csv"),
                ("parameters.csv", "bilinearization_parameters.csv"),
            ):
                assert _rows(result_root / mode / "tables" / actual) == _rows(fixture_root / mode / "data" / expected)
    assert all(_sha(path) == digest for path, digest in before_v1.items())
    assert all(_sha(path) == digest for path, digest in before_outputs.items())
    reuse_args = [*common, "--run-id", "run_002", "--reuse-manifest", str(final / "manifest.json")]
    assert main(["workflow", "plan", *reuse_args]) == 0
    reused = json.loads(capsys.readouterr().out)
    assert {item["status"] for item in reused["plan"]["modules"]} == {"reusable"}
    changed = json.loads((destination / "modules/site_hazard.json").read_text(encoding="utf-8"))
    changed["title"] += " - modified input"
    changed_bytes = json.dumps(changed, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    (destination / "modules/site_hazard.json").write_bytes(changed_bytes)
    for reference in project["references"]:
        if reference["module_id"] == "site_hazard":
            reference["sha256"] = hashlib.sha256(changed_bytes).hexdigest()
    project_file.write_text(yaml.safe_dump(project, sort_keys=False, allow_unicode=True), encoding="utf-8")
    assert main(["workflow", "plan", *reuse_args]) == 0
    invalidated = json.loads(capsys.readouterr().out)
    assert {item["status"] for item in invalidated["plan"]["modules"]} == {"invalidated"}
    assert all(item["reason"] for item in invalidated["plan"]["modules"])
    assert main([*args, "--write"]) == 2
    assert not (ROOT / "outputs/v2/Modelos_constitutivos").exists()


def test_cli_statuses_and_foreign_cwd(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = _template(tmp_path)
    destination = tmp_path / "converted"
    assert main([*_convert_args(template, destination), "--write"]) == 0
    capsys.readouterr()
    project = destination / "project.yaml"
    command = [sys.executable, "-m", "structurelab_pbd_rc", "workflow", "plan", "--project", str(project), "--module", "site_hazard"]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["plan"]["modules"][-1]["status"] == "ready"
    assert main(["workflow", "plan", "--project", str(project), "--module", "ground_motion"]) == 3
    blocked = json.loads(capsys.readouterr().out)
    assert {item["status"] for item in blocked["plan"]["modules"]} >= {"not_implemented"}
    assert main(["workflow", "plan", "--project", str(project), "--module", "ground_motion", "--config", "ground_motion=unused.json"]) == 2
    assert main(["workflow", "plan", "--project", str(project), "--module", "stage_02"]) == 2

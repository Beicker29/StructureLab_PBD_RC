"""Etapa 2 flow tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from structurelab_pbd_rc.design.stages.stage_02_material_characterization import run


def test_stage_02_prepares_output_directories(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/stage_02/material_characterization.yaml"),
        output_root=tmp_path,
    )

    assert result["status"] == "prepared"
    assert result["stage_id"] == "stage_02"
    for name in ("root", "figures", "reports", "data"):
        assert result["output_dirs"][name].exists()
    assert "tables" not in result["output_dirs"]


def test_stage_02_writes_initial_results_json(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/stage_02/material_characterization.yaml"),
        output_root=tmp_path,
    )

    results_path = result["results_path"]
    assert results_path.exists()
    assert results_path == tmp_path / "stage_02" / "data" / "stage_02_results.json"

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    assert payload["stage_id"] == "stage_02"
    assert payload["status"] == "completed"
    assert payload["computed_results"]["concrete_curves"]
    assert payload["metrics"]


def test_stage_02_creates_expected_artifacts(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/stage_02/material_characterization.yaml"),
        output_root=tmp_path,
    )

    expected = [
        "data_concrete_curves",
        "data_steel_curves",
        "data_mesh_curves",
        "data_model_mander_classic_unconfined_concrete_csv",
        "data_model_mander_classic_unconfined_concrete_xlsx",
        "data_model_steel_tension_mander_csv",
        "data_model_steel_tension_mander_xlsx",
        "figure_concrete",
        "figure_steel_buckling",
        "figure_mesh",
        "figure_core_sketch",
        "figure_model_mander_classic_unconfined_concrete",
        "figure_model_mander_classic_confined_concrete",
        "figure_model_mander_adjusted_confined_concrete",
        "figure_model_attard_setunge_unconfined_concrete",
        "figure_model_attard_setunge_confined_concrete",
        "figure_model_steel_tension_mander",
        "figure_model_steel_compression_no_buckling",
        "figure_model_steel_compression_with_buckling",
        "figure_model_welded_wire_mesh",
        "report_model_mander_classic_unconfined_concrete_yaml",
        "report_model_mander_classic_confined_concrete_yaml",
        "report_model_mander_adjusted_confined_concrete_yaml",
        "report_model_attard_setunge_unconfined_concrete_yaml",
        "report_model_attard_setunge_confined_concrete_yaml",
        "report_model_steel_tension_mander_yaml",
        "report_model_steel_compression_no_buckling_yaml",
        "report_model_steel_compression_with_buckling_yaml",
        "report_model_welded_wire_mesh_yaml",
        "report_document_mander_classic_unconfined_concrete_qmd",
        "report_document_mander_classic_unconfined_concrete_pdf",
    ]
    for key in expected:
        assert Path(result["generated_files"][key]).exists()

    assert Path(result["generated_files"]["figure_model_mander_classic_confined_concrete"]).suffix == ".png"
    assert Path(result["generated_files"]["figure_model_mander_classic_confined_concrete"]).parent.name == "models"
    assert (
        Path(result["generated_files"]["report_document_mander_classic_unconfined_concrete_qmd"])
        == tmp_path
        / "stage_02"
        / "reports"
        / "mander_classic_unconfined_concrete"
        / "mander_classic_unconfined_concrete_memoria.qmd"
    )
    assert (
        Path(result["generated_files"]["report_document_mander_classic_unconfined_concrete_pdf"])
        == tmp_path
        / "stage_02"
        / "reports"
        / "mander_classic_unconfined_concrete"
        / "mander_classic_unconfined_concrete_memoria.pdf"
    )
    assert (
        Path(result["generated_files"]["data_model_mander_classic_unconfined_concrete_csv"]).parent
        == tmp_path / "stage_02" / "data" / "models" / "mander_classic_unconfined_concrete"
    )
    assert "report_pdf" not in result["generated_files"]
    assert "report_calculated_parameters_yaml" not in result["generated_files"]
    assert not (tmp_path / "stage_02" / "reports" / "documento").exists()
    assert not (tmp_path / "stage_02" / "reports" / "models").exists()


def test_stage_02_reports_model_parameters_without_global_report(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/stage_02/material_characterization.yaml"),
        output_root=tmp_path,
    )

    report_path = Path(result["generated_files"]["report_model_mander_classic_unconfined_concrete_yaml"])
    payload = yaml.safe_load(report_path.read_text(encoding="utf-8"))

    assert payload["stage_id"] == "stage_02"
    assert payload["model"]["key"] == "mander_classic_unconfined_concrete"
    assert payload["datos_de_entrada"]["f_co"] == 28.0
    assert payload["datos_de_salida"]["r"]["value"] > 0
    assert payload["datos_de_salida"]["constitutive_function"]["branches"]
    assert "display" not in payload["datos_de_salida"]["constitutive_function"]
    assert not (tmp_path / "stage_02" / "reports" / "stage_02_calculated_parameters.yaml").exists()
    assert not (tmp_path / "stage_02" / "reports" / "stage_02_report.pdf").exists()


def test_stage_02_writes_one_yaml_per_constitutive_model(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/stage_02/material_characterization.yaml"),
        output_root=tmp_path,
    )

    mander_path = Path(result["generated_files"]["report_model_mander_classic_confined_concrete_yaml"])
    mander_payload = yaml.safe_load(mander_path.read_text(encoding="utf-8"))

    assert (
        mander_path
        == tmp_path
        / "stage_02"
        / "reports"
        / "mander_classic_confined_concrete"
        / "mander_classic_confined_concrete.yaml"
    )
    assert mander_payload["model"]["key"] == "mander_classic_confined_concrete"
    assert mander_payload["datos_de_salida"]["fcc"]["value"] > 0
    assert mander_payload["datos_de_salida"]["parametros_de_confinamiento"]["parameters"]["ke"]["equation"]
    assert mander_payload["datos_de_salida"]["geometria_resuelta"]["data"]["confined_core"]
    assert "supporting_parameters" not in mander_payload

    steel_path = Path(result["generated_files"]["report_model_steel_tension_mander_yaml"])
    steel_payload = yaml.safe_load(steel_path.read_text(encoding="utf-8"))

    assert steel_payload["model"]["key"] == "steel_tension_mander"
    assert steel_payload["datos_de_salida"]["Et"]["equation"]
    assert "supporting_parameters" not in steel_payload


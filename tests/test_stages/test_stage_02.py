"""Etapa 2 flow tests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from structurelab_pbd_rc.design.stages.stage_02_section_characterization import run
from structurelab_pbd_rc.reports.export_excel import write_xlsx


def _write_stage_02_config(tmp_path: Path) -> Path:
    workbook_path = tmp_path / "m_phi.xlsx"
    write_xlsx(
        [
            {"phi_pos": 0.0, "M_pos": 0.0, "phi_neg": 0.0, "M_neg": 0.0},
            {"phi_pos": 0.001, "M_pos": 80.0, "phi_neg": -0.001, "M_neg": -75.0},
            {"phi_pos": 0.002, "M_pos": 140.0, "phi_neg": -0.002, "M_neg": -130.0},
            {"phi_pos": 0.004, "M_pos": 180.0, "phi_neg": -0.004, "M_neg": -170.0},
            {"phi_pos": 0.008, "M_pos": 165.0, "phi_neg": -0.008, "M_neg": -160.0},
            {"phi_pos": 0.010, "M_pos": 145.0, "phi_neg": -0.010, "M_neg": -150.0},
        ],
        workbook_path,
        sheet_name="Curva",
    )
    config = {
        "stage_id": "stage_02",
        "title": "Caracterizacion de la seccion por diagrama momento-curvatura",
        "units": {"curvature": "1/m", "moment": "kN-m"},
        "source": {"workbook": str(workbook_path), "sheets": "all"},
        "curve_detection": {
            "title_row": 1,
            "header_row": 1,
            "first_data_row": 2,
            "curvature_header_contains": "phi",
            "moment_header_contains": "M_",
        },
        "bilinearization": {
            "method": "asce_fema_energy_equivalent_m_phi",
            "stiffness_fraction": 0.60,
            "tolerance": 0.05,
            "search_points": 1000,
            "my_lower_ratio": 0.05,
            "my_upper_ratio": 1.00,
            "ultimate": {"mode": "final_valid_point"},
        },
    }
    config_path = tmp_path / "stage_02.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_stage_02_runs_and_writes_moment_curvature_outputs(tmp_path: Path) -> None:
    config_path = _write_stage_02_config(tmp_path)
    output_root = tmp_path / "outputs"
    stale_file = output_root / "stage_02" / "old_sheet" / "data" / "stale.csv"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")

    result = run(config_path=config_path, output_root=output_root)
    sheet = result["sheets"][0]
    generated = sheet["generated_files"]

    assert result["stage_id"] == "stage_02"
    assert result["status"] == "completed"
    assert result["sheet_count"] == 1
    assert result["curve_count"] == 2
    assert sheet["sheet"] == "Curva"
    assert Path(generated["data_moment_curvature_curves"]).exists()
    assert Path(generated["data_bilinear_curves"]).exists()
    assert Path(generated["data_bilinearization_parameters"]).exists()
    assert Path(generated["figure_moment_curvature_real"]).exists()
    assert Path(generated["figure_moment_curvature_bilinearization"]).exists()
    assert Path(generated["figure_moment_curvature_real_vs_bilinear"]).exists()
    assert Path(generated["report_positive_bending_yaml"]).exists()
    assert Path(generated["report_negative_bending_yaml"]).exists()
    assert Path(generated["data_sheet_results_json"]).exists()
    assert result["results_path"] == output_root / "stage_02" / "data" / "stage_02_results.json"
    assert not stale_file.exists()
    assert not (output_root / "stage_02" / "figures").exists()
    assert not (output_root / "stage_02" / "reports").exists()
    assert (output_root / "stage_02" / "Curva" / "figures").exists()
    assert (output_root / "stage_02" / "Curva" / "reports").exists()

    payload = json.loads(result["results_path"].read_text(encoding="utf-8"))
    assert payload["stage_id"] == "stage_02"
    assert payload["method"] == "asce_fema_energy_equivalent_m_phi"
    assert payload["sheet_count"] == 1
    assert payload["curve_count"] == 2


def test_stage_02_report_contains_input_and_output_sections(tmp_path: Path) -> None:
    config_path = _write_stage_02_config(tmp_path)
    result = run(config_path=config_path, output_root=tmp_path / "outputs")

    report_path = Path(result["sheets"][0]["generated_files"]["report_positive_bending_yaml"])
    report = yaml.safe_load(report_path.read_text(encoding="utf-8"))

    assert report["datos_de_entrada"]["curvature_column"] == "A"
    assert report["datos_de_entrada"]["sheet"] == "Curva"
    assert report["datos_de_salida"]["Ke"]["equation"] == "Ke = M_60My / phi_60My"
    assert report["datos_de_salida"]["phi_y"]["equation"] == "phi_y = My / Ke"
    assert report["datos_de_salida"]["alpha"]["equation"] == "alpha = Kp / Ke"
    assert report["datos_de_salida"]["constitutive_function"]["branches"]

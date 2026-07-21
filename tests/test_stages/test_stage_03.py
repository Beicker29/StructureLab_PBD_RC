"""Etapa 3 flow tests."""

from __future__ import annotations

import json
import csv
from pathlib import Path

import yaml

from structurelab_pbd_rc.design.stages.stage_03_section_characterization import run
from structurelab_pbd_rc.reports.export_excel import write_xlsx


def _write_stage_03_config(tmp_path: Path) -> Path:
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
        "stage_id": "stage_03",
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
        "cyclic_diagram": {
            "enabled": True,
            "cut_points_by_sheet": {
                "Curva": {
                    "positive_bending": {"phi": 0.006, "moment": 170.0},
                    "negative_bending": {"phi": "auto", "moment": "auto"},
                }
            },
        },
    }
    config_path = tmp_path / "stage_03.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_stage_03_runs_and_writes_moment_curvature_outputs(tmp_path: Path) -> None:
    config_path = _write_stage_03_config(tmp_path)
    output_root = tmp_path / "outputs"
    stale_file = output_root / "stage_03" / "old_sheet" / "data" / "stale.csv"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")

    result = run(config_path=config_path, output_root=output_root)
    sheet = result["sheets"][0]
    generated = sheet["generated_files"]

    assert result["stage_id"] == "stage_03"
    assert result["status"] == "completed"
    assert result["sheet_count"] == 1
    assert result["curve_count"] == 2
    assert sheet["sheet"] == "Curva"
    assert Path(generated["data_moment_curvature_curves"]).exists()
    assert Path(generated["data_bilinear_curves"]).exists()
    assert Path(generated["data_bilinearization_parameters"]).exists()
    assert Path(generated["data_ciclica_moment_curvature_curves"]).exists()
    assert Path(generated["data_ciclica_bilinear_curves"]).exists()
    assert Path(generated["data_ciclica_bilinearization_parameters"]).exists()
    assert Path(generated["data_ciclica_cut_points"]).exists()
    assert Path(generated["figure_moment_curvature_real"]).exists()
    assert Path(generated["figure_moment_curvature_bilinearization"]).exists()
    assert Path(generated["figure_moment_curvature_real_vs_bilinear"]).exists()
    assert Path(generated["figure_ciclica_moment_curvature_real"]).exists()
    assert Path(generated["figure_ciclica_moment_curvature_bilinearization"]).exists()
    assert Path(generated["figure_ciclica_moment_curvature_real_vs_bilinear"]).exists()
    assert Path(generated["report_positive_bending_yaml"]).exists()
    assert Path(generated["report_negative_bending_yaml"]).exists()
    assert Path(generated["data_sheet_results_json"]).exists()
    assert result["results_path"] == output_root / "stage_03" / "data" / "stage_03_results.json"
    assert not stale_file.exists()
    assert not (output_root / "stage_03" / "figures").exists()
    assert not (output_root / "stage_03" / "reports").exists()
    assert not (output_root / "stage_03" / "Curva" / "data").exists()
    assert not (output_root / "stage_03" / "Curva" / "figures").exists()
    assert not (output_root / "stage_03" / "Curva" / "reports").exists()
    assert (output_root / "stage_03" / "Curva" / "monotonica" / "data").exists()
    assert (output_root / "stage_03" / "Curva" / "monotonica" / "figures").exists()
    assert (output_root / "stage_03" / "Curva" / "monotonica" / "reports").exists()
    assert (output_root / "stage_03" / "Curva" / "ciclica" / "data").exists()
    assert (output_root / "stage_03" / "Curva" / "ciclica" / "figures").exists()
    assert (output_root / "stage_03" / "Curva" / "ciclica" / "reports").exists()

    with Path(generated["data_bilinearization_parameters"]).open("r", encoding="utf-8", newline="") as file:
        monotonic_parameter_rows = list(csv.DictReader(file))
    curve_names = {row["curve_id"]: row["curve_name"] for row in monotonic_parameter_rows}
    assert curve_names["positive_bending"] == "Curva"
    assert curve_names["negative_bending"] == "Curva-INV"

    with Path(generated["data_ciclica_moment_curvature_curves"]).open("r", encoding="utf-8", newline="") as file:
        cyclic_rows = list(csv.DictReader(file))
    positive_rows = [row for row in cyclic_rows if row["curve_id"] == "positive_bending"]
    assert float(positive_rows[-1]["phi"]) == 0.006
    assert float(positive_rows[-1]["moment"]) == 170.0

    with Path(generated["data_ciclica_bilinear_curves"]).open("r", encoding="utf-8", newline="") as file:
        cyclic_bilinear_rows = list(csv.DictReader(file))
    positive_bilinear_rows = [row for row in cyclic_bilinear_rows if row["curve_id"] == "positive_bending"]
    assert positive_bilinear_rows[-1]["point"] == "ultimate"
    assert float(positive_bilinear_rows[-1]["phi"]) == 0.006
    assert float(positive_bilinear_rows[-1]["moment"]) == 170.0

    with Path(generated["data_ciclica_bilinearization_parameters"]).open("r", encoding="utf-8", newline="") as file:
        cyclic_parameter_rows = list(csv.DictReader(file))
    positive_parameters = next(row for row in cyclic_parameter_rows if row["curve_id"] == "positive_bending")
    assert float(positive_parameters["phi_u"]) == 0.006
    assert float(positive_parameters["Mu"]) == 170.0
    assert float(positive_parameters["phi_u_ciclico"]) == 0.006
    assert float(positive_parameters["Mu_ciclico"]) == 170.0

    with Path(generated["data_ciclica_cut_points"]).open("r", encoding="utf-8", newline="") as file:
        cut_rows = list(csv.DictReader(file))
    positive_cut = next(row for row in cut_rows if row["curve_id"] == "positive_bending")
    assert positive_cut["mode"] == "configured"
    assert float(positive_cut["phi"]) == 0.006
    assert float(positive_cut["moment"]) == 170.0
    assert float(positive_cut["phi_u_ciclico"]) == 0.006
    assert float(positive_cut["Mu_ciclico"]) == 170.0

    payload = json.loads(result["results_path"].read_text(encoding="utf-8"))
    assert payload["stage_id"] == "stage_03"
    assert payload["method"] == "asce_fema_energy_equivalent_m_phi"
    assert payload["sheet_count"] == 1
    assert payload["curve_count"] == 2


def test_stage_03_report_contains_input_and_output_sections(tmp_path: Path) -> None:
    config_path = _write_stage_03_config(tmp_path)
    result = run(config_path=config_path, output_root=tmp_path / "outputs")

    report_path = Path(result["sheets"][0]["generated_files"]["report_positive_bending_yaml"])
    report = yaml.safe_load(report_path.read_text(encoding="utf-8"))

    assert report["datos_de_entrada"]["curvature_column"] == "A"
    assert report["datos_de_entrada"]["sheet"] == "Curva"
    assert report["datos_de_salida"]["Ke"]["equation"] == "Ke = M_60My / phi_60My"
    assert report["datos_de_salida"]["phi_y"]["equation"] == "phi_y = My / Ke"
    assert report["datos_de_salida"]["alpha"]["equation"] == "alpha = Kp / Ke"
    assert report["datos_de_salida"]["constitutive_function"]["branches"]

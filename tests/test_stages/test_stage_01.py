"""Etapa 1 hazard flow tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml

from structurelab_pbd_rc.design.stages.stage_01_hazard import run


def _write_case_01_config(tmp_path: Path, *, service_factor: float = 0.35, maximum_factor: float = 1.50) -> Path:
    config = {
        "stage_id": "stage_01",
        "case_id": "case_01_nsr10",
        "title": "Espectros NSR-10",
        "units": {"period": "s", "spectral_acceleration": "g"},
        "hazard": {
            "seismic": {
                "source": {"code": "NSR-10"},
                "period_range": {"start": 0.0, "end": 0.05, "step": 0.01},
                "nsr10_parameters": {
                    "Aa": 0.25,
                    "Av": 0.25,
                    "Fa": 1.0,
                    "Fv": 1.0,
                    "importance_factor": 1.0,
                    "soil_profile": "B",
                },
                "hazard_levels": {
                    "service": {"name": "Servicio", "return_period_years": 31, "scale_factor": service_factor},
                    "design": {"name": "Diseno", "return_period_years": 475, "scale_factor": 1.0},
                    "maximum_considered": {
                        "name": "Maximo considerado",
                        "return_period_years": 2500,
                        "scale_factor": maximum_factor,
                    },
                },
            },
        },
    }
    path = tmp_path / "case_01.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _write_case_02_config(tmp_path: Path) -> Path:
    config = {
        "stage_id": "stage_01",
        "case_id": "case_02_sgc_ccp14",
        "title": "Espectros SGC CCP-14",
        "units": {"period": "s", "spectral_acceleration": "g"},
        "hazard": {
            "seismic": {
                "source": {"hazard_provider": "SGC", "spectral_shape_code": "CCP-14"},
                "period_range": {"start": 0.0, "end": 1.0, "step": 0.2},
                "site": {"profile": "B"},
                "hazard_levels": {
                    "service": {
                        "name": "Servicio",
                        "return_period_years": 31,
                        "PGA": 0.10,
                        "Sa_0_2": 0.30,
                        "Sa_1_0": 0.15,
                    },
                    "design": {
                        "name": "Diseno",
                        "return_period_years": 475,
                        "PGA": 0.20,
                        "Sa_0_2": 0.60,
                        "Sa_1_0": 0.30,
                    },
                    "maximum_considered": {
                        "name": "Maximo considerado",
                        "return_period_years": 2500,
                        "PGA": 0.30,
                        "Sa_0_2": 0.90,
                        "Sa_1_0": 0.45,
                    },
                },
            },
        },
    }
    path = tmp_path / "case_02.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_stage_01_case_01_scales_design_spectrum(tmp_path: Path) -> None:
    config_path = _write_case_01_config(tmp_path)
    result = run(config_path=config_path, output_root=tmp_path / "outputs")

    spectra_path = Path(result["generated_files"]["case_01_spectra_csv"])
    rows = _read_csv(spectra_path)

    assert result["stage_id"] == "stage_01"
    assert result["case_id"] == "case_01_nsr10"
    assert Path(result["generated_files"]["case_01_spectra_xlsx"]).exists()
    assert Path(result["generated_files"]["case_01_spectra_figure"]).exists()
    assert Path(result["generated_files"]["case_01_service_spectrum_figure"]).exists()
    assert Path(result["generated_files"]["case_01_design_spectrum_figure"]).exists()
    assert Path(result["generated_files"]["case_01_maximum_considered_spectrum_figure"]).exists()
    assert Path(result["generated_files"]["case_01_report_yaml"]).exists()
    assert spectra_path.parent == tmp_path / "outputs" / "stage_01" / "nsr10_spectra" / "data"
    assert result["results_path"] == (
        tmp_path / "outputs" / "stage_01" / "nsr10_spectra" / "data" / "stage_01_results.json"
    )
    assert (tmp_path / "outputs" / "stage_01" / "ccp14_spectra").exists()
    assert not (tmp_path / "outputs" / "stage_01" / "data").exists()
    assert not (tmp_path / "outputs" / "stage_01" / "figures").exists()
    assert not (tmp_path / "outputs" / "stage_01" / "reports").exists()
    for row in rows:
        design = float(row["Sa_diseno_475"])
        assert float(row["Sa_servicio_31"]) == pytest.approx(0.35 * design)
        assert float(row["Sa_maximo_considerado_2500"]) == pytest.approx(1.50 * design)


def test_stage_01_case_01_scaling_factors_are_editable(tmp_path: Path) -> None:
    base_result = run(config_path=_write_case_01_config(tmp_path / "base"), output_root=tmp_path / "base_outputs")
    edited_result = run(
        config_path=_write_case_01_config(tmp_path / "edited", service_factor=0.50, maximum_factor=1.80),
        output_root=tmp_path / "edited_outputs",
    )

    base_rows = _read_csv(Path(base_result["generated_files"]["case_01_spectra_csv"]))
    edited_rows = _read_csv(Path(edited_result["generated_files"]["case_01_spectra_csv"]))

    for base, edited in zip(base_rows, edited_rows):
        assert float(base["Sa_diseno_475"]) == pytest.approx(float(edited["Sa_diseno_475"]))
        assert float(edited["Sa_servicio_31"]) == pytest.approx(0.50 * float(edited["Sa_diseno_475"]))
        assert float(edited["Sa_maximo_considerado_2500"]) == pytest.approx(1.80 * float(edited["Sa_diseno_475"]))


def test_stage_01_case_02_uses_independent_sgc_values(tmp_path: Path) -> None:
    result = run(config_path=_write_case_02_config(tmp_path), output_root=tmp_path / "outputs")

    rows = _read_csv(Path(result["generated_files"]["case_02_spectra_csv"]))
    parameters = _read_csv(Path(result["generated_files"]["case_02_parameters_csv"]))

    assert result["case_id"] == "case_02_sgc_ccp14"
    assert Path(result["generated_files"]["case_02_spectra_xlsx"]).exists()
    assert Path(result["generated_files"]["case_02_spectra_figure"]).exists()
    assert Path(result["generated_files"]["case_02_service_spectrum_figure"]).exists()
    assert Path(result["generated_files"]["case_02_design_spectrum_figure"]).exists()
    assert Path(result["generated_files"]["case_02_maximum_considered_spectrum_figure"]).exists()
    assert Path(result["generated_files"]["case_02_report_yaml"]).exists()
    assert Path(result["generated_files"]["case_02_spectra_csv"]).parent == (
        tmp_path / "outputs" / "stage_01" / "ccp14_spectra" / "data"
    )
    assert (tmp_path / "outputs" / "stage_01" / "nsr10_spectra").exists()
    assert [float(row["period_s"]) for row in rows] == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    by_period = {int(row["return_period_years"]): row for row in parameters}
    assert float(by_period[31]["Sa_at_T_0"]) == pytest.approx(0.10)
    assert float(by_period[475]["Sa_at_T_0_2"]) == pytest.approx(0.60)
    assert float(by_period[2500]["Sa_at_T_1_0"]) == pytest.approx(0.45)

    payload = json.loads(Path(result["results_path"]).read_text(encoding="utf-8"))
    assert payload["case_id"] == "case_02_sgc_ccp14"


def test_stage_01_case_02_requires_sgc_values_only_for_that_case(tmp_path: Path) -> None:
    incomplete = {
        "stage_id": "stage_01",
        "case_id": "case_02_sgc_ccp14",
        "title": "Incomplete",
        "units": {"period": "s", "spectral_acceleration": "g"},
        "hazard": {
            "seismic": {
                "source": {"hazard_provider": "SGC", "spectral_shape_code": "CCP-14"},
                "period_range": {"start": 0.0, "end": 1.0, "step": 0.1},
                "site": {"profile": "B"},
                "hazard_levels": {
                    "service": {
                        "name": "Servicio",
                        "return_period_years": 31,
                        "PGA": None,
                        "Sa_0_2": None,
                        "Sa_1_0": None,
                    },
                    "design": {
                        "name": "Diseno",
                        "return_period_years": 475,
                        "PGA": 0.20,
                        "Sa_0_2": 0.60,
                        "Sa_1_0": 0.30,
                    },
                    "maximum_considered": {
                        "name": "Maximo considerado",
                        "return_period_years": 2500,
                        "PGA": 0.30,
                        "Sa_0_2": 0.90,
                        "Sa_1_0": 0.45,
                    },
                },
            },
        },
    }
    path = tmp_path / "incomplete_case_02.yaml"
    path.write_text(yaml.safe_dump(incomplete, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing SGC hazard parameters"):
        run(config_path=path, output_root=tmp_path / "outputs")

    result = run(config_path=_write_case_01_config(tmp_path / "case_01"), output_root=tmp_path / "case_01_outputs")
    assert result["case_id"] == "case_01_nsr10"


def test_stage_01_case_02_rejects_profile_f(tmp_path: Path) -> None:
    config_path = _write_case_02_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["hazard"]["seismic"]["site"]["profile"] = "F"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="profile F"):
        run(config_path=config_path, output_root=tmp_path / "outputs")

"""Configuration loading tests."""

from __future__ import annotations

from pathlib import Path

from structurelab_pbd_rc.io.read_config import load_json_config, load_yaml_config


def test_stage_01_nsr10_config_is_nested_under_hazard_seismic() -> None:
    config = load_yaml_config(Path("configs/stage_01/case_01_nsr10_spectra.yaml"))

    seismic = config["hazard"]["seismic"]

    assert config["stage_id"] == "stage_01"
    assert config["case_id"] == "case_01_nsr10"
    assert config["units"] == {"period": "s", "spectral_acceleration": "g"}
    assert seismic["source"]["code"] == "NSR-10"
    assert seismic["period_range"] == {"start": 0.0, "end": 5.0, "step": 0.01}
    assert seismic["nsr10_parameters"]["soil_profile"] in {"A", "B", "C", "D", "E"}
    assert seismic["hazard_levels"]["service"]["return_period_years"] == 31
    assert "nsr10_parameters" not in config
    assert "hazard_levels" not in config


def test_stage_01_sgc_ccp14_config_is_independent_case() -> None:
    config = load_yaml_config(Path("configs/stage_01/case_02_sgc_ccp14_spectra.yaml"))

    seismic = config["hazard"]["seismic"]

    assert config["stage_id"] == "stage_01"
    assert config["case_id"] == "case_02_sgc_ccp14"
    assert seismic["source"]["hazard_provider"] == "Servicio Geologico Colombiano"
    assert seismic["source"]["spectral_shape_code"] == "CCP-14"
    assert seismic["site"]["profile"] in {"A", "B", "C", "D", "E"}
    levels = seismic["hazard_levels"]
    assert [levels[key]["return_period_years"] for key in ("service", "design", "maximum_considered")] == [
        31,
        475,
        2500,
    ]
    for record in levels.values():
        assert "Fpga" not in record
        assert "Fa" not in record
        assert "Fv" not in record
    assert "hazard_records" not in seismic
    assert "hazard_records" not in config


def test_stage_03_config_contains_excel_bilinearization_inputs() -> None:
    config = load_yaml_config(Path("configs/stage_03/section_characterization.yaml"))

    assert config["stage_id"] == "stage_03"
    assert config["units"] == {"curvature": "1/m", "moment": "kN-m"}
    assert config["source"]["workbook"] == "references/stage_03/excel/M-curvatura.xlsx"
    assert config["source"]["sheets"] == "all"
    assert config["curve_detection"]["title_row"] == 1
    assert config["curve_detection"]["header_row"] == 2
    assert config["curve_detection"]["first_data_row"] == 4
    assert config["curve_detection"]["curvature_header_contains"] == "Curvature"
    assert config["curve_detection"]["moment_header_contains"] == "Moment"
    assert config["bilinearization"]["method"] == "asce_fema_energy_equivalent_m_phi"
    assert config["bilinearization"]["stiffness_fraction"] == 0.60
    assert config["bilinearization"]["tolerance"] == 0.0010
    assert config["bilinearization"]["ultimate"]["post_peak_strength_ratio"] == 0.80
    assert config["cyclic_diagram"]["enabled"] is True
    assert "V2" in config["cyclic_diagram"]["cut_points_by_sheet"]
    assert "positive_bending" in config["cyclic_diagram"]["cut_points_by_sheet"]["V2"]


def test_stage_02_rdm_json_has_required_input_identifiers() -> None:
    config = load_json_config(
        Path(
            "configs/stage_02/ductile_reinforcing_steel/monotonic/"
            "steel_compression_rdm_2019_monotonic.json"
        )
    )

    assert config["enabled"] is True
    assert config["units"] == {"length": "mm", "stress": "MPa", "strain": "mm/mm"}
    assert config["inputs"]["project_id"] == "default"
    assert config["inputs"]["case_id"] == "rdm_2019_ld5"
    assert config["inputs"]["model_id"] == "steel_compression_rdm_2019_monotonic"
    parameters = config["inputs"]["parameters"]
    assert parameters["tie_spacing_mm"] == 100.0
    assert parameters["tie_bar_diameter_mm"] == 10.0
    assert parameters["effective_tie_leg_length_mm"] == 200.0
    assert parameters["effective_tie_legs"] == 2
    assert parameters["restrained_longitudinal_bars"] == 2
    assert parameters["tie_steel_modulus_MPa"] == 200000.0
    assert parameters["buckling_restraint_case"] == "bending"
    for derived in (
        "epsilon_y",
        "buckling_intervals",
        "unsupported_length_mm",
        "l_over_d",
        "L_over_D",
        "rb",
    ):
        assert derived not in parameters

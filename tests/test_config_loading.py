"""Configuration loading tests."""

from __future__ import annotations

from pathlib import Path

from structurelab_pbd_rc.io.read_config import load_yaml_config


def test_workshop_01_config_contains_pdf_data() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))

    assert config["workshop_id"] == "workshop_01"
    assert config["base_section"]["dimensions"]["width"]["value"] == 75.0
    assert config["concrete"]["compressive_strength"]["value"] == 28.0
    assert config["longitudinal_reinforcement"]["count"] == 16
    assert config["longitudinal_reinforcement"]["steel"]["expected_yield_strength"]["value"] == 470.30
    assert config["longitudinal_reinforcement"]["steel"]["yield_strain"]["value"] == 0.0024
    assert config["longitudinal_reinforcement"]["steel"]["hardening_start_stress"]["value"] == 472.16
    assert config["longitudinal_reinforcement"]["steel"]["ultimate_strength"]["value"] == 659.74
    assert config["longitudinal_reinforcement"]["steel"]["ultimate_strain"]["value"] == 0.1141
    assert config["longitudinal_reinforcement"]["steel"]["strain_hardening"]["parameter_p"]["value"] == 3.087
    assert config["transverse_reinforcement"]["spacing"]["value"] == 10.0
    assert config["welded_wire_mesh"]["mechanical_properties"][5]["fy_mpa"] == 610.0
    assert config["outputs"]["initial_results_file"] == "data/workshop_01_results.json"
    assert "pending_implementation" in config

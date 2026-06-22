"""Configuration loading tests."""

from __future__ import annotations

from pathlib import Path

from structurelab_pbd_rc.io.read_config import load_yaml_config


def test_workshop_01_config_contains_pdf_data() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))

    assert config["workshop_id"] == "workshop_01"
    assert config["units"] == {"length": "mm", "force": "kN", "moment": "kN-m", "stress": "MPa", "strain": "mm/mm"}
    assert config["section"]["width"] == 750.0
    assert config["section"]["confined_core"]["clear_spacing_wi"]["values"]
    assert "note" not in config["section"]["confined_core"]["clear_spacing_wi"]
    assert "assumptions" not in config["section"]
    assert config["concrete"]["f_co"] == 28.0
    assert config["concrete"]["ft_expression"] == "0.62 * sqrt(f_co)"
    assert config["concrete"]["Et_expression"] == "Ec"
    assert config["concrete"]["epsilon_t_expression"] == "ft / Et"
    assert config["concrete"]["epsilon_sp"] == 0.005
    assert "epsilon_cu_unconfined" not in config["concrete"]
    assert config["longitudinal_reinforcement"]["count"] == 16
    assert config["longitudinal_reinforcement"]["steel"]["fy"] == 470.30
    assert config["longitudinal_reinforcement"]["steel"]["epsilon_y"] == 0.0024
    assert config["longitudinal_reinforcement"]["steel"]["f_sh"] == 472.16
    assert config["longitudinal_reinforcement"]["steel"]["f_su"] == 659.74
    assert config["longitudinal_reinforcement"]["steel"]["epsilon_su"] == 0.1141
    assert config["longitudinal_reinforcement"]["steel"]["P"] == 3.087
    assert config["transverse_reinforcement"]["spacing"] == 100.0
    assert config["welded_wire_mesh"]["mechanical_properties"][5]["fy"] == 610.0
    assert "confinement" in config["model_inputs"]
    assert "mander_classic_confined_concrete" in config["model_inputs"]
    assert "attard_setunge_confined_concrete" in config["model_inputs"]
    assert "steel_tension_mander" in config["model_inputs"]
    assert "welded_wire_mesh" in config["model_inputs"]
    assert "outputs" not in config
    assert "pending_implementation" not in config

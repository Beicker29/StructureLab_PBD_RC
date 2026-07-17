"""Geometry tests for Etapa 2."""

from pathlib import Path

from structurelab_pbd_rc.io.read_config import load_yaml_config
from structurelab_pbd_rc.design.stages.stage_02_material_characterization import build_geometry_and_confinement


def test_stage_02_geometry_is_positive() -> None:
    config = load_yaml_config(Path("configs/stage_02/material_characterization.yaml"))
    geometry, confinement = build_geometry_and_confinement(config)

    assert geometry["gross_section"]["area_cm2"] == 75.0 * 75.0
    assert geometry["confined_core"]["width_cm"] > 0
    assert geometry["longitudinal_reinforcement"]["total_area_cm2"] > 0
    assert geometry["longitudinal_ratio"] > 0
    assert confinement["rho_s"] > 0
    assert 0 < confinement["ke"] <= 1
    assert confinement["fl_eff_mpa"] > 0
    expected_wi_count = len(config["section"]["confined_core"]["clear_spacing_wi"]["values"])
    assert len(confinement["wi_cm"]) == expected_wi_count
    assert confinement["sum_wi2_cm2"] == sum(wi**2 for wi in confinement["wi_cm"])


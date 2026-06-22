"""Material curve tests for Taller 1."""

from inspect import getsource
from math import isclose
from pathlib import Path

from structurelab_pbd_rc.io.read_config import load_yaml_config
from structurelab_pbd_rc.mechanics.materials.concrete.attard_setunge import AttardSetungeConcreteModel, AttardSetungeParameters
from structurelab_pbd_rc.mechanics.materials.library.mesh_database import get_mesh_properties
from structurelab_pbd_rc.mechanics.materials.steel.compression_models import SteelCompressionModel
from structurelab_pbd_rc.mechanics.materials.steel.tension_models import ManderSteelTensionModel, SteelTensionParameters
from structurelab_pbd_rc.mechanics.materials.steel.welded_wire_mesh import CarrilloWeldedWireMeshModel, WeldedWireMeshParameters
from structurelab_pbd_rc.design.workshops.workshop_01_material_characterization import (
    _steel_post_yield_modulus,
    build_geometry_and_confinement,
    generate_material_curves,
)


def test_curves_are_non_empty_and_positive() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    _, confinement = build_geometry_and_confinement(config)
    concrete_curves, steel_curves, mesh_curves = generate_material_curves(config, confinement)

    for curve_group in (concrete_curves, steel_curves, mesh_curves):
        for curve_name, curve in curve_group.items():
            assert curve["strain"]
            assert curve["stress"]
            if curve_name == "mander_classic_unconfined_concrete":
                assert min(curve["stress"]) < 0
            else:
                assert min(curve["stress"]) >= 0
            assert max(curve["stress"]) > 0


def test_mander_classic_increases_confined_strength() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    _, confinement = build_geometry_and_confinement(config)
    concrete_curves, _, _ = generate_material_curves(config, confinement)

    fc = config["concrete"]["f_co"]
    fcc = concrete_curves["mander_classic_confined_concrete"]["parameters"]["fcc_mpa"]
    assert fcc > fc


def test_unconfined_mander_uses_spalling_and_tension_inputs() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    _, confinement = build_geometry_and_confinement(config)
    concrete_curves, _, _ = generate_material_curves(config, confinement)

    curve = concrete_curves["mander_classic_unconfined_concrete"]
    parameters = curve["parameters"]
    fc = float(config["concrete"]["f_co"])
    ec = 4700.0 * fc**0.5
    ft = 0.62 * fc**0.5

    assert isclose(parameters["f_co_mpa"], fc, rel_tol=1e-12)
    assert isclose(parameters["ft_mpa"], ft, rel_tol=1e-12)
    assert isclose(parameters["Et_mpa"], ec, rel_tol=1e-12)
    assert isclose(parameters["epsilon_t"], ft / ec, rel_tol=1e-12)
    assert parameters["tension_sign_convention"] == "negative"
    assert isclose(parameters["epsilon_t_plot"], -ft / ec, rel_tol=1e-12)
    assert isclose(parameters["ft_plot_mpa"], -ft, rel_tol=1e-12)
    assert isclose(parameters["epsilon_2co"], 2.0 * config["concrete"]["epsilon_co"], rel_tol=1e-12)
    assert isclose(parameters["epsilon_sp"], config["concrete"]["epsilon_sp"], rel_tol=1e-12)
    assert isclose(curve["strain"][0], -ft / ec, rel_tol=1e-12)
    assert isclose(curve["stress"][0], -ft, rel_tol=1e-12)
    assert isclose(curve["strain"][-1], config["concrete"]["epsilon_sp"], rel_tol=1e-12)
    assert isclose(curve["stress"][-1], 0.0, abs_tol=1e-12)


def test_attard_confined_uses_attard_setunge_strength_equation() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    _, confinement = build_geometry_and_confinement(config)
    concrete_curves, _, _ = generate_material_curves(config, confinement)

    fc = float(config["concrete"]["f_co"])
    fl = float(confinement["fl_eff_mpa"])
    expected_fcc = fc * (1.0 + 10.0 * (fl / fc) ** 0.6)
    attard_fcc = concrete_curves["attard_setunge_confined_concrete"]["parameters"]["f_peak_mpa"]
    mander_adjusted_fcc = concrete_curves["mander_adjusted_confined_concrete"]["parameters"]["fcc_mpa"]

    assert isclose(attard_fcc, expected_fcc, rel_tol=1e-12)
    assert not isclose(attard_fcc, mander_adjusted_fcc, rel_tol=1e-6)


def test_attard_confined_reaches_descending_control_points() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    _, confinement = build_geometry_and_confinement(config)
    concrete_curves, _, _ = generate_material_curves(config, confinement)

    curve = concrete_curves["attard_setunge_confined_concrete"]
    parameters = curve["parameters"]
    eps_2i = float(parameters["epsilon_2i"])
    f_2i = float(parameters["f_2i_mpa"])

    fc = float(config["concrete"]["f_co"])
    assert isclose(float(parameters["fpl_mpa"]), 0.45 * fc, rel_tol=1e-12)
    assert isclose(float(parameters["epsilon_u"]), eps_2i, rel_tol=1e-12)
    assert isclose(curve["strain"][-1], eps_2i, rel_tol=1e-12)
    assert isclose(curve["stress"][-1], f_2i, rel_tol=1e-8)


def test_attard_confined_ascending_coefficients_use_same_expressions() -> None:
    model = AttardSetungeConcreteModel(
        AttardSetungeParameters(
            f_c_mpa=28.0,
            elastic_modulus_mpa=4700.0 * 28.0**0.5,
            epsilon_peak=0.002,
            confined=True,
            confinement_pressure_mpa=1.359427952175688,
        )
    )
    parameters = model.summary_parameters()

    as_expected = float(parameters["Eti_mpa"]) * float(parameters["epsilon_peak"]) / float(parameters["f_peak_mpa"])
    alpha = float(parameters["alpha"])
    fpl_ratio = float(parameters["fpl_mpa"]) / float(parameters["f_peak_mpa"])
    one_minus = 1.0 - fpl_ratio
    bs_expected = ((as_expected - 1.0) ** 2) / (alpha * one_minus**2)
    bs_expected += (as_expected**2 * (1.0 - alpha)) / (alpha**2 * fpl_ratio * one_minus)
    bs_expected -= 1.0
    cs_expected = as_expected - 2.0
    ds_expected = bs_expected + 1.0

    as_actual, bs_actual, cs_actual, ds_actual = model.ascending_coefficients()

    assert isclose(as_actual, as_expected, rel_tol=1e-12)
    assert isclose(bs_actual, bs_expected, rel_tol=1e-12)
    assert isclose(cs_actual, cs_expected, rel_tol=1e-12)
    assert isclose(ds_actual, ds_expected, rel_tol=1e-12)


def test_steel_tension_matches_mander_piecewise_expression() -> None:
    model = ManderSteelTensionModel(
        SteelTensionParameters(
            fy_mpa=470.0,
            fu_mpa=590.0,
            elastic_modulus_mpa=200000.0,
            strain_hardening_modulus_mpa=2000.0,
            epsilon_sh=0.01,
            epsilon_su=0.10,
            parameter_p=4.0,
        )
    )
    eps_y = 470.0 / 200000.0

    elastic_strain = 0.5 * eps_y
    hardening_strain = 0.5 * (eps_y + 0.01)
    ultimate_branch_strain = 0.055
    expected_ultimate_branch = 590.0 - (590.0 - 470.0) * ((0.10 - ultimate_branch_strain) / (0.10 - 0.01)) ** 4.0

    assert isclose(model.stress_at_strain(elastic_strain), 200000.0 * elastic_strain, rel_tol=1e-12)
    assert isclose(
        model.stress_at_strain(hardening_strain),
        470.0 + 2000.0 * (hardening_strain - eps_y),
        rel_tol=1e-12,
    )
    assert isclose(model.stress_at_strain(ultimate_branch_strain), expected_ultimate_branch, rel_tol=1e-12)
    assert isclose(model.stress_at_strain(0.10), 590.0, rel_tol=1e-12)
    assert model.stress_at_strain(0.101) == 0.0


def test_steel_compression_model_does_not_import_tension_model() -> None:
    source = getsource(SteelCompressionModel)

    assert "ManderSteelTensionModel" not in source
    assert "SteelTensionParameters" not in source


def test_mesh_uses_diameter_specific_ultimate_strength() -> None:
    for diameter in (4, 5, 6):
        properties = get_mesh_properties(diameter)
        model = CarrilloWeldedWireMeshModel(
            WeldedWireMeshParameters(
                diameter_mm=diameter,
                fy_mpa=float(properties["fy_mpa"]),
                fu_mpa=float(properties["fu_mpa"]),
                epsilon_u=float(properties["epsilon_u"]),
            )
        )

        assert model.summary_parameters()["fu_mpa"] == properties["fu_mpa"]
        assert isclose(model.stress_at_strain(float(properties["epsilon_u"])), float(properties["fu_mpa"]), rel_tol=1e-12)
        assert model.stress_at_strain(float(properties["epsilon_u"]) + 0.001) == 0.0


def test_generated_steel_and_mesh_curves_stop_at_model_ultimate_strain() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    _, confinement = build_geometry_and_confinement(config)
    _, steel_curves, mesh_curves = generate_material_curves(config, confinement)

    assert isclose(steel_curves["steel_tension_mander"]["strain"][-1], 0.1141, rel_tol=1e-12)
    assert isclose(steel_curves["steel_compression_no_buckling"]["strain"][-1], 0.08, rel_tol=1e-12)
    assert isclose(steel_curves["steel_compression_with_buckling"]["strain"][-1], 0.08, rel_tol=1e-12)
    assert isclose(mesh_curves["welded_wire_mesh"]["strain"][-1], 0.0113, rel_tol=1e-12)


def test_generated_longitudinal_steel_uses_mu_column_values() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    _, confinement = build_geometry_and_confinement(config)
    _, steel_curves, _ = generate_material_curves(config, confinement)

    parameters = steel_curves["steel_tension_mander"]["parameters"]
    expected_et = (472.16 - 470.30) / (0.0138 - 0.0024)

    assert isclose(parameters["fy_mpa"], 470.30, rel_tol=1e-12)
    assert isclose(parameters["fu_mpa"], 659.74, rel_tol=1e-12)
    assert isclose(parameters["eps_y"], 0.0024, rel_tol=1e-12)
    assert isclose(parameters["eps_sh"], 0.0138, rel_tol=1e-12)
    assert isclose(parameters["eps_su"], 0.1141, rel_tol=1e-12)
    assert isclose(parameters["P"], 3.087, rel_tol=1e-12)
    assert isclose(parameters["Et_mpa"], expected_et, rel_tol=1e-12)


def test_longitudinal_steel_et_uses_fsh_minus_fy_over_epssh_minus_epsy() -> None:
    config = load_yaml_config(Path("configs/workshops/workshop_01_material_characterization.yaml"))
    steel = config["longitudinal_reinforcement"]["steel"]

    expected_et = (steel["f_sh"] - steel["fy"]) / (steel["epsilon_sh"] - steel["epsilon_y"])

    assert steel["Et"]["value"] == "auto"
    assert steel["Et"]["expression"] == "(f_sh - f_y) / (epsilon_sh - epsilon_y)"
    assert isclose(_steel_post_yield_modulus(steel), expected_et, rel_tol=1e-12)


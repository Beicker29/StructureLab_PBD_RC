"""Tests for the source-based RDM 2019 monotonic envelope."""

from __future__ import annotations

from copy import deepcopy

import pytest

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.mechanics.materials.common import MaterialProvenance
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019 import (
    RDM2019MonotonicCompressionModel,
    RDM2019Parameters,
    RDM2019SectionModelSet,
)


PROVENANCE = MaterialProvenance(
    source="Akkaya, Guner and Vecchio (2019)",
    citation="jp116.pdf, Table 2",
    source_location="references/stage_02/ductile_reinforcing_steel/monotonic/",
    specimen_or_profile="Equation verification",
    calibration_status="source_equation_validation_case",
)


def _parameters(**overrides: object) -> RDM2019Parameters:
    values: dict[str, object] = {
        "fy_mpa": 420.0,
        "fu_mpa": 630.0,
        "epsilon_y": 0.0021,
        "epsilon_sh": 0.01,
        "epsilon_su": 0.10,
        "parameter_p": 4.0,
        "longitudinal_bar_diameter_mm": 20.0,
        "tie_bar_diameter_mm": 10.0,
        "tie_spacing_mm": 100.0,
        "effective_tie_leg_length_mm": 200.0,
        "effective_tie_legs": 2,
        "restrained_longitudinal_bars": 2,
        "tie_steel_modulus_mpa": 200000.0,
        "buckling_restraint_case": "bending",
        "provenance": PROVENANCE,
    }
    values.update(overrides)
    return RDM2019Parameters(**values)


def _model(l_over_d: float, **overrides: object) -> RDM2019MonotonicCompressionModel:
    """Create a physical n=1 equation case with the requested L/D."""

    return RDM2019MonotonicCompressionModel(
        _parameters(
            tie_spacing_mm=20.0 * l_over_d,
            tie_bar_diameter_mm=25.0,
            effective_tie_leg_length_mm=50.0,
            effective_tie_legs=10,
            restrained_longitudinal_bars=1,
            tie_steel_modulus_mpa=10_000_000.0,
            **overrides,
        )
    )


def test_es_is_always_derived_from_fy_and_epsilon_y() -> None:
    parameters = _parameters(fy_mpa=470.30, epsilon_y=0.0024)

    assert parameters.elastic_modulus_mpa == pytest.approx(195958.33333333334)
    assert parameters.buckling_result.elastic_modulus_mpa == pytest.approx(
        parameters.elastic_modulus_mpa
    )


def test_input_validation_rejects_inconsistent_mechanical_properties() -> None:
    with pytest.raises(ConfigError, match="fy_MPa <= fu_MPa"):
        _parameters(fy_mpa=700.0)
    with pytest.raises(ConfigError, match="epsilon_y <= epsilon_sh"):
        _parameters(epsilon_sh=0.002)
    with pytest.raises(ConfigError, match="epsilon_y"):
        _parameters(epsilon_y=0.0)
    with pytest.raises(ConfigError, match="parameter_p"):
        _parameters(parameter_p=-0.1)


@pytest.mark.parametrize("forbidden", ["Es_MPa", "buckling_intervals", "L_over_D"])
def test_single_model_config_rejects_derived_inputs(forbidden: str) -> None:
    parameters = {
        "fy_MPa": 420.0,
        "fu_MPa": 630.0,
        "epsilon_y": 0.0021,
        "epsilon_sh": 0.01,
        "epsilon_su": 0.10,
        "parameter_p": 4.0,
        "longitudinal_bar_diameter_mm": 20.0,
        "tie_bar_diameter_mm": 10.0,
        "tie_spacing_mm": 100.0,
        "effective_tie_leg_length_mm": 200.0,
        "effective_tie_legs": 2,
        "restrained_longitudinal_bars": 2,
        "tie_steel_modulus_MPa": 200000.0,
        "buckling_restraint_case": "bending",
        forbidden: 1.0,
    }
    with pytest.raises(ConfigError, match="cannot receive derived values"):
        RDM2019MonotonicCompressionModel.from_config(
            {"parameters": parameters, "provenance": PROVENANCE.as_dict()}
        )


def test_elastic_response_and_signed_quadrants() -> None:
    model = _model(8.0)

    compression_magnitude = model.response(0.001)
    tension = model.tension_response(0.03)
    compression = model.signed_compression_response(-0.03)

    assert compression_magnitude.stress_mpa == pytest.approx(200.0)
    assert compression_magnitude.tangent_mpa == pytest.approx(200000.0)
    assert tension.stress_mpa > 0.0
    assert compression.stress_mpa < 0.0
    assert abs(compression.stress_mpa) < tension.stress_mpa
    assert compression.diagnostics["buckling_restraint_case"] == "bending"
    with pytest.raises(MaterialDomainError, match="cannot be negative"):
        model.tension_response(-0.001)
    with pytest.raises(MaterialDomainError, match="cannot be positive"):
        model.signed_compression_response(0.001)


def test_reference_tension_branch_uses_input_parameter_p() -> None:
    model = _model(8.0, parameter_p=3.087)
    strain = 0.05
    expected = 630.0 + (420.0 - 630.0) * (
        (0.10 - strain) / (0.10 - 0.01)
    ) ** 3.087

    assert model.tension_response(0.01).stress_mpa == pytest.approx(420.0)
    assert model.tension_response(strain).stress_mpa == pytest.approx(expected)
    summary = model.summary_parameters()
    assert summary["parameter_p"] == pytest.approx(3.087)
    assert summary["special_case_parameter_p"] == 1.0


def test_l_over_d_activation_threshold_follows_jp116() -> None:
    no_buckling = _model(4.99)
    buckling = _model(5.0)

    assert no_buckling.buckling_active is False
    assert no_buckling.epsilon_i is None
    assert buckling.buckling_active is True
    assert buckling.parameters.resolved_l_over_d == pytest.approx(5.0)


def test_table_2_controls_match_independent_equations() -> None:
    model = _model(12.0)
    summary = model.summary_parameters()
    rb = 12.0 * (420.0 / 100.0) ** 0.5
    epsilon_i_0 = 0.0021 * (55.0 - 2.3 * rb)
    epsilon_i = max(7.0 * 0.0021, epsilon_i_0)
    alpha_1 = 0.8 + 1.8 * (630.0 / 420.0) / 12.0
    alpha_2 = 1.1 - 0.016 * rb

    assert summary["rb"] == pytest.approx(rb)
    assert summary["eps_i"] == pytest.approx(epsilon_i)
    assert summary["alpha_1"] == pytest.approx(alpha_1)
    assert summary["alpha_2"] == pytest.approx(alpha_2)
    assert summary["alpha"] == pytest.approx(alpha_1 * alpha_2)
    assert 0.2 * 420.0 <= summary["f_i_mpa"] <= summary["f_it_mpa"]


def test_epsilon_i_correction_and_special_alpha_case() -> None:
    corrected = _model(6.0, epsilon_su=0.06)
    assert corrected.epsilon_i_0 is not None
    assert corrected.epsilon_i_max is not None
    assert corrected.epsilon_i_0 < corrected.parameters.epsilon_su < corrected.epsilon_i_max
    assert corrected.epsilon_i == pytest.approx(
        corrected.epsilon_i_0
        * corrected.parameters.epsilon_su
        / corrected.epsilon_i_max
    )

    special = _model(12.0, epsilon_su=0.02)
    assert special.epsilon_i is not None
    assert special.alpha_2 is not None
    expected_f_it = 630.0 + (420.0 - 630.0) * (
        (0.02 - special.epsilon_i) / (0.02 - 0.01)
    )
    assert special.uses_special_alpha_case is True
    assert special.f_it_mpa == pytest.approx(expected_f_it)
    assert special.alpha == pytest.approx(
        0.75 * special.alpha_2 * (expected_f_it / 420.0)
    )


def test_piecewise_compression_is_continuous_at_all_transitions() -> None:
    model = _model(12.0)
    eps_i = model.epsilon_i
    eps_ii = model.epsilon_ii
    f_i = model.f_i_mpa
    assert eps_i is not None and eps_ii is not None and f_i is not None

    assert model.stress_at_strain(model.parameters.epsilon_y) == pytest.approx(420.0)
    assert model.stress_at_strain(eps_i) == pytest.approx(f_i)
    assert model.stress_at_strain(eps_ii) == pytest.approx(0.75 * f_i)
    for transition in (model.parameters.epsilon_y, eps_i, eps_ii):
        left = model.stress_at_strain(transition - 1.0e-9)
        right = model.stress_at_strain(transition + 1.0e-9)
        assert left == pytest.approx(right, abs=5.0e-4)


def test_residual_floor_and_ultimate_domain_policy() -> None:
    model = _model(20.0)

    assert model.stress_at_strain(0.10) == pytest.approx(84.0)
    assert model.stress_at_strain(0.100001) == 0.0
    assert model.tangent_at_strain(0.10) == 0.0


def test_generated_curve_and_notable_points_share_calculated_controls() -> None:
    model = _model(12.0)
    curve = model.generate_curve(num_points=101)
    notable = {point["id"]: point for point in model.notable_response_points()}

    assert len(curve["strain"]) == 101
    assert curve["strain"][-1] == 0.10
    assert notable["compression_intermediate"]["strain"] == pytest.approx(
        -model.epsilon_i
    )
    assert notable["compression_intermediate"]["stress_mpa"] == pytest.approx(
        -model.f_i_mpa
    )
    with pytest.raises(ConfigError, match="at least 2"):
        model.generate_curve(num_points=1)
    with pytest.raises(ConfigError, match="cannot exceed epsilon_su"):
        model.generate_curve(max_strain=0.12)


def test_col75_section_builds_both_documented_restraint_cases() -> None:
    config = {
        "parameters": {
            "fy_MPa": 470.30,
            "fu_MPa": 659.74,
            "epsilon_y": 0.0024,
            "epsilon_sh": 0.0138,
            "epsilon_su": 0.1141,
            "parameter_p": 3.087,
            "longitudinal_bar_diameter_mm": 22.225,
            "tie_bar_diameter_mm": 12.7,
            "tie_spacing_mm": 100.0,
            "tie_steel_modulus_MPa": 200000.0,
            "restraint_cases": {
                "bending": {
                    "effective_tie_leg_length_mm": 657.3,
                    "effective_tie_legs": 4,
                    "restrained_longitudinal_bars": 5,
                },
                "pure_compression": {
                    "effective_tie_leg_length_mm": 657.3,
                    "effective_tie_legs": 4,
                    "restrained_longitudinal_bars": 5,
                },
            },
        },
        "provenance": PROVENANCE.as_dict(),
    }
    section = RDM2019SectionModelSet.from_config(config)
    bending = section.models["bending"].summary_parameters()
    axial = section.models["pure_compression"].summary_parameters()

    assert section.parameters.elastic_modulus_mpa == pytest.approx(195958.33333333334)
    assert section.parameters.parameter_p == pytest.approx(3.087)
    assert bending["buckling_intervals"] == 2
    assert bending["L_over_D"] == pytest.approx(8.998875140607424)
    assert axial["buckling_intervals"] == 3
    assert axial["L_over_D"] == pytest.approx(13.498312710911135)
    assert axial["f_i_mpa"] < bending["f_i_mpa"]
    assert "eps_y" not in bending

    incomplete = deepcopy(config)
    incomplete["parameters"]["restraint_cases"].pop("pure_compression")
    with pytest.raises(ConfigError, match="pure_compression"):
        RDM2019SectionModelSet.from_config(incomplete)

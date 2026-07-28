"""Tests for the RDM 2019 monotonic compression envelope."""

from __future__ import annotations

import warnings

import pytest

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.mechanics.materials.common import MaterialProvenance
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019 import (
    RDM2019MonotonicCompressionModel,
    RDM2019Parameters,
)


PROVENANCE = MaterialProvenance(
    source="Akkaya, Guner and Vecchio (2019)",
    citation="DOI 10.14359/51711143",
    source_location="Table 2",
    specimen_or_profile="Equation verification",
    calibration_status="source_equation_validation_case",
)


def _parameters(**overrides: object) -> RDM2019Parameters:
    values: dict[str, object] = {
        "fy_mpa": 420.0,
        "fu_mpa": 630.0,
        "elastic_modulus_mpa": 200000.0,
        "epsilon_y": 0.0021,
        "epsilon_sh": 0.01,
        "epsilon_su": 0.10,
        "parameter_p": 4.0,
        "longitudinal_bar_diameter_mm": 20.0,
        "buckling_intervals": 1,
        "tie_spacing_mm": 100.0,
        "provenance": PROVENANCE,
    }
    values.update(overrides)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return RDM2019Parameters(**values)


def _model(l_over_d: float) -> RDM2019MonotonicCompressionModel:
    return RDM2019MonotonicCompressionModel(
        _parameters(buckling_intervals=1, tie_spacing_mm=20.0 * l_over_d)
    )


def test_input_validation_rejects_inconsistent_mechanical_properties() -> None:
    with pytest.raises(ConfigError, match="Es_MPa"):
        _parameters(elastic_modulus_mpa=0.0)
    with pytest.raises(ConfigError, match="fy_MPa <= fu_MPa"):
        _parameters(fy_mpa=700.0)
    with pytest.raises(ConfigError, match="epsilon_y < epsilon_sh"):
        _parameters(epsilon_sh=0.002)
    with pytest.raises(ConfigError, match="consistent with fy_MPa / Es_MPa"):
        _parameters(epsilon_y=0.0022)


def test_legacy_l_over_d_is_derived_only_from_n_s_and_d() -> None:
    parameters = _parameters(buckling_intervals=2, tie_spacing_mm=50.0)

    assert parameters.resolved_unsupported_length_mm == 100.0
    assert parameters.resolved_l_over_d == 5.0
    assert (
        parameters.l_over_d_source == "legacy input n; L=n*s; L/D=(n*s)/D"
    )

    with pytest.raises(ConfigError, match="positive integer"):
        _parameters(buckling_intervals=1.5)
    with pytest.raises(ConfigError, match="tie_spacing_mm must be positive"):
        _parameters(tie_spacing_mm=0.0)


def test_elastic_response_and_compression_positive_convention() -> None:
    model = _model(5.0)
    response = model.response(0.001)

    assert response.stress_mpa == pytest.approx(200.0)
    assert response.tangent_mpa == pytest.approx(200000.0)
    assert response.diagnostics["sign_convention"] == "compression_positive"
    with pytest.raises(MaterialDomainError, match="cannot be negative"):
        model.stress_at_strain(-0.001)


def test_signed_tension_and_compression_responses_use_physical_quadrants() -> None:
    model = _model(12.0)

    tension = model.tension_response(0.03)
    compression = model.signed_compression_response(-0.03)

    assert tension.strain > 0.0
    assert tension.stress_mpa > 0.0
    assert tension.diagnostics["stress_state"] == "tension"
    assert compression.strain < 0.0
    assert compression.stress_mpa < 0.0
    assert compression.diagnostics["stress_state"] == "compression"
    assert abs(compression.stress_mpa) < tension.stress_mpa
    with pytest.raises(MaterialDomainError, match="cannot be negative"):
        model.tension_response(-0.001)
    with pytest.raises(MaterialDomainError, match="cannot be positive"):
        model.signed_compression_response(0.001)


def test_l_over_d_below_five_uses_reference_envelope_without_buckling() -> None:
    model = _model(4.99)
    strain = 0.05
    expected = 630.0 + (420.0 - 630.0) * ((0.10 - strain) / (0.10 - 0.01)) ** 4

    assert model.buckling_active is False
    assert model.stress_at_strain(strain) == pytest.approx(expected)
    assert model.summary_parameters()["eps_i"] is None


def test_l_over_d_five_activates_rdm_and_matches_table_2_controls() -> None:
    model = _model(5.0)
    summary = model.summary_parameters()

    assert model.buckling_active is True
    assert summary["eps_y"] == pytest.approx(0.0021)
    assert summary["rb"] == pytest.approx(10.2469508)
    assert summary["eps_i"] == pytest.approx(0.06600723)
    assert summary["f_it_mpa"] == pytest.approx(625.7264)
    assert summary["f_i_mpa"] == pytest.approx(526.8083)
    assert summary["eps_ii"] == pytest.approx(0.09893274)
    assert summary["residual_stress_mpa"] == 84.0


def test_l_over_d_twelve_matches_table_2_controls_and_degrades_more() -> None:
    model_5 = _model(5.0)
    model_12 = _model(12.0)
    summary = model_12.summary_parameters()

    assert summary["rb"] == pytest.approx(24.5926818)
    assert summary["eps_i"] == pytest.approx(0.0147)
    assert summary["f_it_mpa"] == pytest.approx(460.5485)
    assert summary["f_i_mpa"] == pytest.approx(304.1556)
    assert summary["eps_ii"] == pytest.approx(0.03370973)
    assert model_12.epsilon_i < model_5.epsilon_i
    assert model_12.stress_at_strain(0.03) < model_5.stress_at_strain(0.03)


def test_epsilon_i_correction_is_applied_in_its_strict_interval() -> None:
    model = RDM2019MonotonicCompressionModel(
        _parameters(tie_spacing_mm=120.0, epsilon_su=0.06)
    )
    epsilon_i_0 = model.epsilon_i_0
    epsilon_i_max = model.epsilon_i_max
    assert epsilon_i_0 is not None and epsilon_i_max is not None

    assert epsilon_i_0 < model.parameters.epsilon_su < epsilon_i_max
    assert model.epsilon_i == pytest.approx(
        epsilon_i_0 * model.parameters.epsilon_su / epsilon_i_max
    )


def test_special_alpha_case_has_priority_and_uses_p_one_reference() -> None:
    model = RDM2019MonotonicCompressionModel(
        _parameters(tie_spacing_mm=240.0, epsilon_su=0.02)
    )
    epsilon_i = model.epsilon_i
    alpha_2 = model.alpha_2
    f_it = model.f_it_mpa
    assert epsilon_i is not None and alpha_2 is not None and f_it is not None

    expected_f_it = 630.0 + (420.0 - 630.0) * ((0.02 - epsilon_i) / (0.02 - 0.01))
    assert model.uses_special_alpha_case is True
    assert f_it == pytest.approx(expected_f_it)
    assert model.alpha == pytest.approx(0.75 * alpha_2 * (f_it / 420.0))


def test_piecewise_stress_is_continuous_at_transition_points() -> None:
    model = _model(12.0)
    eps_y = model.parameters.epsilon_y
    eps_i = model.epsilon_i
    eps_ii = model.epsilon_ii
    f_i = model.f_i_mpa
    assert eps_y is not None and eps_i is not None and eps_ii is not None and f_i is not None

    assert model.stress_at_strain(eps_y) == pytest.approx(420.0)
    assert model.stress_at_strain(eps_i) == pytest.approx(f_i)
    assert model.stress_at_strain(eps_ii) == pytest.approx(0.75 * f_i)

    step = 1e-9
    for transition in (eps_y, eps_i, eps_ii):
        left = model.stress_at_strain(transition - step)
        right = model.stress_at_strain(transition + step)
        assert left == pytest.approx(right, abs=5e-4)


def test_residual_floor_and_ultimate_domain_policy() -> None:
    model = _model(20.0)

    assert model.stress_at_strain(0.10) == pytest.approx(84.0)
    assert model.stress_at_strain(0.100001) == 0.0
    assert model.tangent_at_strain(0.10) == 0.0


def test_generated_curve_ends_at_its_own_ultimate_strain() -> None:
    model = _model(12.0)
    curve = model.generate_curve(num_points=101)

    assert len(curve["strain"]) == 101
    assert curve["strain"][-1] == 0.10
    assert curve["stress"][-1] == pytest.approx(model.stress_at_strain(0.10))
    with pytest.raises(ConfigError, match="at least 2"):
        model.generate_curve(num_points=1)
    with pytest.raises(ConfigError, match="cannot exceed epsilon_su"):
        model.generate_curve(max_strain=0.12)


def test_model_is_monotonic_and_has_no_history_api() -> None:
    model = _model(5.0)
    summary = model.summary_parameters()

    assert summary["loading_type"] == "monotonic"
    assert summary["sign_convention"] == "compression_positive"
    assert not hasattr(model, "commit_state")
    assert not hasattr(model, "revert_to_last_commit")
    assert not hasattr(model, "evaluate_history")


def test_applicability_warnings_are_visible_without_changing_response() -> None:
    model = RDM2019MonotonicCompressionModel(
        _parameters(longitudinal_bar_diameter_mm=10.0)
    )

    warnings = model.applicability_warnings()

    assert any("diameter" in warning.lower() for warning in warnings)
    assert model.stress_at_strain(0.01) > 0.0

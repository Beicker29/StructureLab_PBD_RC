"""Tests for the Mander et al. (1988) monotonic concrete envelope."""

from __future__ import annotations

from math import isclose, pi, sqrt

import pytest

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.mechanics.materials.common import MaterialProvenance
from structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic.mander_1988 import (
    Mander1988MonotonicConfinedConcrete,
    Mander1988Parameters,
    calculate_circular_confinement,
    calculate_rectangular_confinement,
)


PROVENANCE = MaterialProvenance(
    source="Mander, Priestley and Park (1988)",
    citation="Theoretical Stress-Strain Model for Confined Concrete",
    source_location=(
        "references/stage_02/confined_concrete/monotonic/"
        "Mander_Priestley_Park_StressStrainModelforConfinedConcrete.pdf"
    ),
    specimen_or_profile="Synthetic equation verification",
    calibration_status="source_equation_validation_case",
)


def _rectangular_geometry(
    *,
    core_width_mm: float = 500.0,
    core_depth_mm: float = 500.0,
    transverse_legs_x: int = 2,
    transverse_legs_y: int = 2,
) -> dict[str, object]:
    return {
        "section_type": "rectangular",
        "core_width_mm": core_width_mm,
        "core_depth_mm": core_depth_mm,
        "tie_bar_diameter_mm": 10.0,
        "tie_spacing_mm": 100.0,
        "transverse_legs_x": transverse_legs_x,
        "transverse_legs_y": transverse_legs_y,
        "longitudinal_steel_area_mm2": 4000.0,
        "clear_spacing_wi_mm": [100.0] * 16,
    }


def _model(
    geometry: dict[str, object] | None = None,
) -> Mander1988MonotonicConfinedConcrete:
    return Mander1988MonotonicConfinedConcrete(
        Mander1988Parameters(
            f_co_mpa=28.0,
            epsilon_co=0.002,
            elastic_modulus_mpa=5000.0 * sqrt(28.0),
            tensile_strength_mpa=3.28,
            f_yh_mpa=420.0,
            epsilon_su_transverse=0.10,
            geometry=geometry or _rectangular_geometry(),
            provenance=PROVENANCE,
        )
    )


def test_rectangular_confinement_matches_published_geometry_equations() -> None:
    geometry = _rectangular_geometry()
    result = calculate_rectangular_confinement(geometry, f_yh_mpa=420.0)

    tie_area = pi * 10.0**2 / 4.0
    rho_cc = 4000.0 / (500.0 * 500.0)
    rho_x = 2.0 * tie_area / (500.0 * 100.0)
    rho_y = rho_x
    expected_ke = (
        (1.0 - 16.0 * 100.0**2 / (6.0 * 500.0 * 500.0))
        * (1.0 - 90.0 / (2.0 * 500.0)) ** 2
        / (1.0 - rho_cc)
    )
    expected_fl = 0.5 * expected_ke * (rho_x + rho_y) * 420.0

    assert result.rho_cc == pytest.approx(rho_cc)
    assert result.rho_x == pytest.approx(rho_x)
    assert result.rho_y == pytest.approx(rho_y)
    assert result.rho_s == pytest.approx(rho_x + rho_y)
    assert result.k_e == pytest.approx(expected_ke)
    assert result.f_l_mpa == pytest.approx(expected_fl)


def test_unequal_rectangular_pressures_use_scalar_effective_pressure() -> None:
    geometry = _rectangular_geometry(
        core_width_mm=600.0,
        core_depth_mm=400.0,
        transverse_legs_x=2,
        transverse_legs_y=2,
    )
    result = calculate_rectangular_confinement(geometry, f_yh_mpa=420.0)
    model = _model(geometry)

    assert result.f_lx_mpa != pytest.approx(result.f_ly_mpa)
    assert result.f_l_mpa == pytest.approx(
        0.5 * result.k_e * (result.rho_x + result.rho_y) * 420.0
    )
    assert model.summary_parameters()["f_l_mpa"] == pytest.approx(
        result.f_l_mpa
    )


@pytest.mark.parametrize(
    ("reinforcement", "arching_exponent"),
    [("circular_hoops", 2), ("spiral", 1)],
)
def test_circular_confinement_matches_hoop_and_spiral_equations(
    reinforcement: str,
    arching_exponent: int,
) -> None:
    geometry = {
        "section_type": "circular",
        "transverse_reinforcement": reinforcement,
        "core_diameter_mm": 500.0,
        "tie_bar_diameter_mm": 10.0,
        "tie_spacing_mm": 100.0,
        "longitudinal_steel_area_mm2": 3000.0,
    }
    result = calculate_circular_confinement(geometry, f_yh_mpa=420.0)

    tie_area = pi * 10.0**2 / 4.0
    rho_cc = 3000.0 / (pi * 500.0**2 / 4.0)
    expected_ke = (1.0 - 90.0 / (2.0 * 500.0)) ** arching_exponent
    expected_ke /= 1.0 - rho_cc
    expected_rho_s = 4.0 * tie_area / (500.0 * 100.0)

    assert result.k_e == pytest.approx(expected_ke)
    assert result.rho_s == pytest.approx(expected_rho_s)
    assert result.f_l_mpa == pytest.approx(
        0.5 * expected_ke * expected_rho_s * 420.0
    )


def test_peak_controls_and_simplified_ultimate_strain() -> None:
    model = _model()
    summary = model.summary_parameters()
    fl_ratio = summary["f_l_mpa"] / 28.0
    expected_fcc = 28.0 * (
        -1.254
        + 2.254 * sqrt(1.0 + 7.94 * fl_ratio)
        - 2.0 * fl_ratio
    )
    expected_epsilon_cc = 0.002 * (
        1.0 + 5.0 * (expected_fcc / 28.0 - 1.0)
    )
    expected_epsilon_cu = (
        0.004
        + 1.4 * summary["rho_s"] * 420.0 * 0.10 / expected_fcc
    )

    assert summary["elastic_modulus_mpa"] == pytest.approx(
        5000.0 * sqrt(28.0)
    )
    assert summary["f_cc_mpa"] == pytest.approx(expected_fcc)
    assert summary["epsilon_cc"] == pytest.approx(expected_epsilon_cc)
    assert summary["epsilon_cu"] == pytest.approx(expected_epsilon_cu)
    assert model.stress_at_strain(expected_epsilon_cc) == pytest.approx(
        expected_fcc
    )
    assert model.tangent_at_strain(expected_epsilon_cc) == pytest.approx(
        0.0,
        abs=1.0e-9,
    )


def test_signed_response_uses_physical_compression_quadrant() -> None:
    model = _model()
    signed = model.signed_compression_response(-model.peak_confined_strain)

    assert signed.strain < 0.0
    assert signed.stress_mpa == pytest.approx(
        -model.peak_confined_stress_mpa
    )
    assert signed.diagnostics["stress_state"] == "compression"
    assert signed.diagnostics["sign_convention"] == (
        "tension_positive_compression_negative"
    )
    with pytest.raises(MaterialDomainError, match="cannot be positive"):
        model.signed_compression_response(0.001)


def test_tensile_segment_uses_configured_ft_and_elastic_modulus() -> None:
    model = _model()
    response = model.tension_response(-model.tensile_ultimate_strain)

    assert model.tensile_ultimate_strain == pytest.approx(
        3.28 / (5000.0 * sqrt(28.0))
    )
    assert response.stress_mpa == pytest.approx(-3.28)
    assert response.diagnostics["stress_state"] == "tension"
    assert response.diagnostics["sign_convention"] == (
        "compression_positive_tension_negative"
    )


def test_curve_domain_ends_at_simplified_epsilon_cu() -> None:
    model = _model()
    curve = model.generate_curve(num_points=101)

    assert curve["strain"][0] == 0.0
    assert curve["strain"][-1] == pytest.approx(model.ultimate_strain)
    assert curve["stress"][-1] > 0.0
    assert model.stress_at_strain(model.ultimate_strain + 1.0e-8) == 0.0
    with pytest.raises(ConfigError, match="cannot exceed epsilon_cu"):
        model.generate_curve(max_strain=model.ultimate_strain * 1.01)


def test_invalid_geometry_is_rejected_without_silent_capping() -> None:
    geometry = _rectangular_geometry()
    geometry["clear_spacing_wi_mm"] = [5000.0]

    with pytest.raises(ConfigError, match="nonpositive effectively confined"):
        _model(geometry)


def test_model_is_stateless_and_monotonic() -> None:
    model = _model()

    assert model.summary_parameters()["loading_type"] == "monotonic"
    assert not hasattr(model, "commit_state")
    assert not hasattr(model, "evaluate_history")
    assert isclose(model.tangent_at_strain(0.0), 5000.0 * sqrt(28.0))

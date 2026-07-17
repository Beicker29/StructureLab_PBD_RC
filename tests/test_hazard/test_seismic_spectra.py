"""Tests for seismic response-spectrum mechanics."""

from __future__ import annotations

import pytest

from structurelab_pbd_rc.mechanics.hazard.seismic.spectra import (
    ccp14_site_factors,
    ccp14_spectral_acceleration,
    ccp14_transition_parameters,
    generate_period_vector,
    nsr10_spectrum,
    nsr10_transition_parameters,
)


def test_period_vector_is_shared_and_valid() -> None:
    periods = generate_period_vector(0.0, 0.05, 0.01)

    assert periods == [0.0, 0.01, 0.02, 0.03, 0.04, 0.05]


def test_period_vector_rejects_negative_periods_and_zero_step() -> None:
    with pytest.raises(ValueError, match="start"):
        generate_period_vector(-0.1, 1.0, 0.01)
    with pytest.raises(ValueError, match="step"):
        generate_period_vector(0.0, 1.0, 0.0)


def test_nsr10_spectrum_uses_transition_equations() -> None:
    parameters = nsr10_transition_parameters(Aa=0.25, Av=0.25, Fa=1.0, Fv=1.0, importance_factor=1.0)
    periods = [0.0, parameters.T0, parameters.Tc, parameters.TL * 2.0]
    spectrum = nsr10_spectrum(periods, parameters)

    assert spectrum[0] == pytest.approx(0.4 * parameters.Sa_plateau)
    assert spectrum[1] == pytest.approx(parameters.Sa_plateau)
    assert spectrum[2] == pytest.approx(parameters.Sa_plateau)
    assert spectrum[3] == pytest.approx(
        1.2 * parameters.Av * parameters.Fv * parameters.TL * parameters.importance_factor / (periods[3] ** 2)
    )


def test_ccp14_interpolates_site_factors_from_tables() -> None:
    factors = ccp14_site_factors(PGA=0.20, Ss=0.60, S1=0.30, site_profile="D")

    assert factors.Fpga == pytest.approx(1.4)
    assert factors.Fa == pytest.approx(1.32)
    assert factors.Fv == pytest.approx(1.8)


def test_ccp14_uses_interpolated_site_factors() -> None:
    parameters = ccp14_transition_parameters(
        return_period_years=475,
        PGA=0.20,
        Ss=0.60,
        S1=0.30,
        site_profile="D",
    )

    assert parameters.Fpga == pytest.approx(1.4)
    assert parameters.Fa == pytest.approx(1.32)
    assert parameters.Fv == pytest.approx(1.8)
    assert ccp14_spectral_acceleration(0.0, parameters) == pytest.approx(1.4 * 0.20)
    assert parameters.SDS == pytest.approx(1.32 * 0.60)
    assert parameters.SD1 == pytest.approx(1.8 * 0.30)


def test_ccp14_rejects_negative_accelerations() -> None:
    with pytest.raises(ValueError, match="PGA"):
        ccp14_transition_parameters(
            return_period_years=475,
            PGA=-0.1,
            Ss=0.6,
            S1=0.3,
            site_profile="B",
        )


def test_ccp14_rejects_profile_f_without_special_study() -> None:
    with pytest.raises(ValueError, match="profile F"):
        ccp14_transition_parameters(
            return_period_years=475,
            PGA=0.1,
            Ss=0.6,
            S1=0.3,
            site_profile="F",
        )

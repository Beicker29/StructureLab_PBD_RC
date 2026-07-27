"""Tests for the stateful Menegotto-Pinto/Steel02 implementation."""

from __future__ import annotations

import pytest

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.cyclic.menegotto_pinto import (
    MenegottoPinto,
)


def _config() -> dict[str, object]:
    return {
        "parameters": {
            "diameter_mm": 6.0,
            "fy_MPa": 500.0,
            "Es_MPa": 200000.0,
            "b": 0.01,
            "R0": 12.0,
            "cR1": 0.8,
            "cR2": 0.2,
            "a1": 0.05,
            "a2": 1.2,
            "a3": 0.07,
            "a4": 1.3,
        },
        "validity": {"eps_compression_min": -0.006, "eps_tension_max": 0.008},
        "failure": {"policy": "none"},
        "provenance": {
            "source": "OpenSees Steel02 formulation",
            "citation": "OpenSees Steel02 documentation",
            "source_location": "Synthetic algorithm verification parameters",
            "specimen_or_profile": "Synthetic verification profile",
            "calibration_status": "synthetic_algorithm_verification_only",
        },
    }


def test_origin_and_initial_elastic_response() -> None:
    model = MenegottoPinto.from_config(_config())

    origin = model.set_trial_strain(0.0)
    assert origin.stress_mpa == 0.0
    assert origin.tangent_mpa == pytest.approx(200000.0)

    response = model.set_trial_strain(1e-6)
    assert response.stress_mpa == pytest.approx(0.2, rel=1e-8)
    assert response.tangent_mpa == pytest.approx(200000.0, rel=1e-8)


def test_trial_revert_and_commit_are_deterministic() -> None:
    model = MenegottoPinto.from_config(_config())

    first_trial = model.set_trial_strain(0.004)
    reverted = model.revert_to_last_commit()
    repeated_trial = model.set_trial_strain(0.004)

    assert reverted.strain == 0.0
    assert reverted.stress_mpa == 0.0
    assert repeated_trial.stress_mpa == pytest.approx(first_trial.stress_mpa)

    model.commit_state()
    assert model.committed_state.strain == pytest.approx(0.004)


def test_reversal_is_detected_and_history_order_is_preserved() -> None:
    model = MenegottoPinto.from_config(_config())
    history = [0.0, 0.001, 0.004, 0.001, -0.002, 0.0]

    responses = model.evaluate_history(history)

    assert [response.strain for response in responses] == history
    assert responses[3].reversal is True
    assert responses[5].reversal is True
    assert responses[4].stress_mpa < responses[3].stress_mpa


def test_tangent_matches_trial_finite_difference_from_same_committed_state() -> None:
    model = MenegottoPinto.from_config(_config())
    model.set_trial_strain(0.004)
    model.commit_state()
    target = 0.001
    step = 1e-8

    center = model.set_trial_strain(target)
    plus = model.set_trial_strain(target + step)
    minus = model.set_trial_strain(target - step)
    finite_difference = (plus.stress_mpa - minus.stress_mpa) / (2.0 * step)

    assert center.tangent_mpa == pytest.approx(finite_difference, rel=2e-5)


def test_missing_cyclic_calibration_parameter_is_rejected() -> None:
    config = _config()
    config["parameters"].pop("R0")

    with pytest.raises(ConfigError, match="R0"):
        MenegottoPinto.from_config(config)


def test_extrapolation_is_visible_and_repeated_step_is_stable() -> None:
    model = MenegottoPinto.from_config(_config())
    model.set_trial_strain(0.004)
    model.commit_state()

    repeated = model.set_trial_strain(0.004)
    outside = model.set_trial_strain(0.009)

    assert repeated.loading_direction == "stationary"
    assert outside.in_domain is False
    assert any("extrapolated" in warning for warning in outside.warnings)

"""Tests for the modified Ramberg-Osgood monotonic envelope."""

from __future__ import annotations

import pytest

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.monotonic.modified_ramberg_osgood import (
    ModifiedRambergOsgood,
)


def _config() -> dict[str, object]:
    return {
        "parameters": {
            "diameter_mm": 4.0,
            "Es_MPa": 200000.0,
            "fy_MPa": None,
            "yield_definition": "not_used_in_source_model_curve",
            "fu_MPa": 538.0,
            "eps_u": 0.0124,
            "shape_exponent": 20.0,
        },
        "compression": {"policy": "unsupported"},
        "numerical": {"root_tolerance": 1e-13, "max_iterations": 250},
        "provenance": {
            "source": "Carrillo et al. (2019)",
            "citation": "DOI 10.1016/j.conbuildmat.2018.11.096",
            "source_location": "Equation 6 and Table 4",
            "specimen_or_profile": "4 mm wire",
            "calibration_status": "source_reported_monotonic_profile",
        },
    }


def test_source_equation_reaches_origin_and_ultimate_point() -> None:
    model = ModifiedRambergOsgood.from_config(_config())

    assert model.strain_from_stress(0.0) == 0.0
    assert model.strain_from_stress(538.0) == pytest.approx(0.0124)
    assert model.response(0.0).stress_mpa == 0.0
    assert model.response(0.0124).stress_mpa == pytest.approx(538.0)


def test_initial_tangent_is_elastic_modulus() -> None:
    model = ModifiedRambergOsgood.from_config(_config())

    assert model.tangent_from_stress(0.0) == pytest.approx(200000.0)
    assert model.response(1e-6).stress_mpa / 1e-6 == pytest.approx(200000.0, rel=1e-7)


def test_analytical_tangent_matches_finite_difference() -> None:
    model = ModifiedRambergOsgood.from_config(_config())
    strain = 0.006
    step = 1e-7

    finite_difference = (
        model.response(strain + step).stress_mpa
        - model.response(strain - step).stress_mpa
    ) / (2.0 * step)

    assert model.response(strain).tangent_mpa == pytest.approx(finite_difference, rel=2e-5)


def test_compression_and_tensile_extrapolation_are_rejected() -> None:
    model = ModifiedRambergOsgood.from_config(_config())

    with pytest.raises(MaterialDomainError, match="compression is unsupported"):
        model.response(-1e-4)
    with pytest.raises(MaterialDomainError, match="tensile strain"):
        model.response(0.0125)


def test_missing_provenance_or_invalid_ultimate_point_is_rejected() -> None:
    missing_provenance = _config()
    missing_provenance.pop("provenance")
    with pytest.raises(ConfigError):
        ModifiedRambergOsgood.from_config(missing_provenance)

    invalid_endpoint = _config()
    invalid_endpoint["parameters"]["eps_u"] = 0.001
    with pytest.raises(ConfigError, match="fu_MPa / Es_MPa"):
        ModifiedRambergOsgood.from_config(invalid_endpoint)


def test_symmetric_compression_requires_and_reports_explicit_assumption() -> None:
    config = _config()
    config["compression"] = {
        "policy": "symmetric_prebuckling_assumption",
        "compression_strain_limit": 0.002,
        "justification": "Software verification only.",
        "explicit_acceptance": True,
    }
    model = ModifiedRambergOsgood.from_config(config)

    response = model.response(-0.001)

    assert response.stress_mpa == pytest.approx(-model.response(0.001).stress_mpa)
    assert response.branch == "compression_symmetric_prebuckling_assumption"
    assert any("not an NTC 5806 calibration" in warning for warning in response.warnings)

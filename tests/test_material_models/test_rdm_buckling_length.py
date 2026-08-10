"""Tests for the documented unsupported-length calculation used by RDM 2019."""

from __future__ import annotations

from math import inf, nan, pi, sqrt

import pytest

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019 import (
    UnsupportedBucklingLengthCalculator,
    select_buckling_intervals,
)


def _calculate(**overrides: object):
    values: dict[str, object] = {
        "fy_mpa": 420.0,
        "epsilon_y": 420.0 / 200000.0,
        "longitudinal_bar_diameter_mm": 20.0,
        "tie_bar_diameter_mm": 10.0,
        "tie_spacing_mm": 100.0,
        "effective_tie_leg_length_mm": 200.0,
        "effective_tie_legs": 2,
        "restrained_longitudinal_bars": 2,
        "tie_steel_modulus_mpa": 200000.0,
        "buckling_restraint_case": "bending",
    }
    values.update(overrides)
    return UnsupportedBucklingLengthCalculator.calculate(**values)


def test_reference_physical_calculation_matches_independent_values() -> None:
    result = _calculate()

    assert result.epsilon_y == pytest.approx(0.0021)
    assert result.elastic_modulus_mpa == pytest.approx(200000.0)
    assert result.tie_area_mm2 == pytest.approx(78.5398163397)
    assert result.longitudinal_bar_inertia_mm4 == pytest.approx(7853.9816339745)
    assert result.reduced_flexural_rigidity_n_mm2 == pytest.approx(804793631.2009)
    assert result.bar_normalized_stiffness_n_per_mm == pytest.approx(78394.2160852)
    assert result.tie_stiffness_n_per_mm == pytest.approx(78539.8163397)
    assert result.equivalent_stiffness_ratio == pytest.approx(1.0018572831)
    assert result.buckling_intervals == 1
    assert result.unsupported_length_mm == 100.0
    assert result.l_over_d == 5.0
    assert result.rb == pytest.approx(10.2469507660)


def test_b3_beam_column_bending_example_is_reproduced() -> None:
    result = _calculate(
        fy_mpa=447.0,
        epsilon_y=447.0 / 200000.0,
        longitudinal_bar_diameter_mm=19.54,
        tie_bar_diameter_mm=sqrt(4.0 * 100.0 / pi),
        tie_spacing_mm=200.0,
        effective_tie_leg_length_mm=244.72,
        effective_tie_legs=2,
        restrained_longitudinal_bars=4,
        buckling_restraint_case="bending",
    )

    assert result.longitudinal_bar_inertia_mm4 == pytest.approx(7155.96, abs=0.01)
    assert result.reduced_flexural_rigidity_n_mm2 == pytest.approx(
        756_469_993.6, rel=2.0e-6
    )
    assert result.bar_normalized_stiffness_n_per_mm == pytest.approx(9210.88, abs=0.02)
    assert result.tie_stiffness_n_per_mm == pytest.approx(40863.03, abs=0.02)
    assert result.equivalent_stiffness_ratio == pytest.approx(4.44, abs=0.01)
    assert result.buckling_intervals == 1
    assert result.l_over_d == pytest.approx(10.23, abs=0.01)


def test_b3_beam_column_pure_compression_example_is_reproduced() -> None:
    result = _calculate(
        fy_mpa=447.0,
        epsilon_y=447.0 / 200000.0,
        longitudinal_bar_diameter_mm=19.54,
        tie_bar_diameter_mm=sqrt(4.0 * 100.0 / pi),
        tie_spacing_mm=200.0,
        effective_tie_leg_length_mm=444.72,
        effective_tie_legs=2,
        restrained_longitudinal_bars=8,
        buckling_restraint_case="pure_compression",
    )

    assert result.effective_restrained_bars == 16
    assert result.tie_stiffness_n_per_mm == pytest.approx(5621.52, abs=0.02)
    assert result.equivalent_stiffness_ratio == pytest.approx(0.61, abs=0.01)
    assert result.buckling_intervals == 2
    assert result.l_over_d == pytest.approx(20.47, abs=0.01)
    assert result.rb == pytest.approx(43.26, abs=0.03)


def test_col75_section_reproduces_both_restraint_conditions() -> None:
    common = {
        "fy_mpa": 470.30,
        "epsilon_y": 0.0024,
        "longitudinal_bar_diameter_mm": 22.225,
        "tie_bar_diameter_mm": 12.7,
        "tie_spacing_mm": 100.0,
        "effective_tie_leg_length_mm": 657.3,
        "effective_tie_legs": 4,
        "restrained_longitudinal_bars": 5,
        "tie_steel_modulus_mpa": 200000.0,
    }
    bending = UnsupportedBucklingLengthCalculator.calculate(
        **common, buckling_restraint_case="bending"
    )
    axial = UnsupportedBucklingLengthCalculator.calculate(
        **common, buckling_restraint_case="pure_compression"
    )

    assert bending.elastic_modulus_mpa == pytest.approx(195958.33333333334)
    assert bending.effective_restrained_bars == 5
    assert bending.equivalent_stiffness_ratio == pytest.approx(0.24878601889233665)
    assert bending.buckling_intervals == 2
    assert bending.unsupported_length_mm == 200.0
    assert bending.l_over_d == pytest.approx(8.998875140607424)
    assert axial.effective_restrained_bars == 10
    assert axial.equivalent_stiffness_ratio == pytest.approx(0.12439300944616832)
    assert axial.buckling_intervals == 3
    assert axial.unsupported_length_mm == 300.0
    assert axial.l_over_d == pytest.approx(13.498312710911135)


def test_pure_compression_doubles_bars_and_halves_tie_stiffness() -> None:
    bending = _calculate(buckling_restraint_case="bending")
    axial = _calculate(buckling_restraint_case="pure_compression")

    assert axial.effective_restrained_bars == 2 * bending.effective_restrained_bars
    assert axial.tie_stiffness_n_per_mm == pytest.approx(
        0.5 * bending.tie_stiffness_n_per_mm
    )
    assert axial.equivalent_stiffness_ratio == pytest.approx(
        0.5 * bending.equivalent_stiffness_ratio
    )


@pytest.mark.parametrize(
    ("keq", "expected"),
    [
        (0.80, 1),
        (0.20, 2),
        (0.12, 3),
        (0.05, 4),
        (0.02, 5),
        (0.007, 6),
        (0.005, 7),
        (0.0035, 8),
        (0.002, 9),
        (0.001, 10),
    ],
)
def test_each_tabulated_interval(keq: float, expected: int) -> None:
    assert select_buckling_intervals(keq) == expected


@pytest.mark.parametrize(
    ("keq", "expected"),
    [
        (0.7500, 2),
        (0.1649, 3),
        (0.0976, 4),
        (0.0448, 5),
        (0.0084, 6),
        (0.0063, 7),
        (0.0037, 8),
        (0.0031, 9),
        (0.0013, 10),
        (0.0009, 10),
    ],
)
def test_boundaries_select_conservative_higher_mode(keq: float, expected: int) -> None:
    assert select_buckling_intervals(keq) == expected


@pytest.mark.parametrize("invalid", [0.0, -0.1, nan, inf])
def test_interval_selection_rejects_invalid_values(invalid: float) -> None:
    with pytest.raises(ConfigError, match="finite number greater than zero"):
        select_buckling_intervals(invalid)


def test_interval_selection_rejects_values_below_table() -> None:
    with pytest.raises(ConfigError, match="minimum tabulated value 0.0009"):
        select_buckling_intervals(0.000899)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("fy_mpa", 0.0),
        ("epsilon_y", inf),
        ("longitudinal_bar_diameter_mm", -1.0),
        ("tie_bar_diameter_mm", 0.0),
        ("tie_spacing_mm", nan),
        ("effective_tie_leg_length_mm", 0.0),
        ("tie_steel_modulus_mpa", -1.0),
    ],
)
def test_calculator_rejects_invalid_scalar_inputs(key: str, value: float) -> None:
    with pytest.raises(ConfigError):
        _calculate(**{key: value})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("effective_tie_legs", 0),
        ("effective_tie_legs", 1.5),
        ("effective_tie_legs", True),
        ("restrained_longitudinal_bars", 0),
        ("restrained_longitudinal_bars", 2.5),
        ("restrained_longitudinal_bars", False),
    ],
)
def test_calculator_requires_positive_natural_counts(key: str, value: float) -> None:
    with pytest.raises(ConfigError, match="positive integer"):
        _calculate(**{key: value})


def test_calculator_rejects_unsupported_restraint_case() -> None:
    with pytest.raises(ConfigError, match="bending, pure_compression"):
        _calculate(buckling_restraint_case="circular")


def test_more_transverse_stiffness_cannot_increase_n() -> None:
    weaker = _calculate(tie_steel_modulus_mpa=100000.0)
    stronger = _calculate(tie_steel_modulus_mpa=200000.0)

    assert stronger.tie_stiffness_n_per_mm > weaker.tie_stiffness_n_per_mm
    assert stronger.equivalent_stiffness_ratio > weaker.equivalent_stiffness_ratio
    assert stronger.buckling_intervals <= weaker.buckling_intervals

"""Tests for the physical unsupported-length calculation used by RDM 2019."""

from __future__ import annotations

from math import inf, nan, pi, sqrt

import pytest

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.mechanics.materials.common import MaterialProvenance
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019 import (
    RDM2019MonotonicCompressionModel,
    RDM2019Parameters,
    UnsupportedBucklingLengthCalculator,
    select_buckling_intervals,
)


PROVENANCE = MaterialProvenance(
    source="Akkaya, Guner and Vecchio (2019)",
    citation="DOI 10.14359/51711143",
    source_location="Table 2 and User Bulletin 3",
    specimen_or_profile="Synthetic physical-restraint verification",
    calibration_status="source_equation_validation_case",
)


def _physical_parameters(**overrides: object) -> RDM2019Parameters:
    values: dict[str, object] = {
        "fy_mpa": 420.0,
        "fu_mpa": 630.0,
        "elastic_modulus_mpa": 200000.0,
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


def _calculate(**overrides: object):
    values: dict[str, object] = {
        "fy_mpa": 420.0,
        "elastic_modulus_mpa": 200000.0,
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
    assert result.tie_area_mm2 == pytest.approx(78.5398163397)
    assert result.longitudinal_bar_inertia_mm4 == pytest.approx(7853.9816339745)
    assert result.reduced_flexural_rigidity_n_mm2 == pytest.approx(
        804793631.2009
    )
    assert result.bar_normalized_stiffness_n_per_mm == pytest.approx(
        78394.2160852
    )
    assert result.tie_stiffness_n_per_mm == pytest.approx(78539.8163397)
    assert result.equivalent_stiffness_ratio == pytest.approx(1.0018572831)
    assert result.effective_restrained_bars == 2
    assert result.buckling_intervals == 1
    assert result.unsupported_length_mm == 100.0
    assert result.l_over_d == 5.0
    assert result.rb == pytest.approx(10.2469507660)
    assert result.buckling_active is True


def test_b3_beam_column_bending_example_is_reproduced() -> None:
    """Reproduce User Bulletin 3, pages 6-7, before published rounding."""

    result = _calculate(
        fy_mpa=447.0,
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
        756_469_993.6,
        rel=2.0e-6,
    )
    assert result.bar_normalized_stiffness_n_per_mm == pytest.approx(
        9210.88,
        abs=0.02,
    )
    assert result.tie_stiffness_n_per_mm == pytest.approx(40863.03, abs=0.02)
    assert result.equivalent_stiffness_ratio == pytest.approx(4.44, abs=0.01)
    assert result.buckling_intervals == 1
    assert result.l_over_d == pytest.approx(10.23, abs=0.01)
    assert result.rb == pytest.approx(21.63, abs=0.02)


def test_b3_beam_column_pure_compression_example_is_reproduced() -> None:
    """Reproduce User Bulletin 3, pages 6-7, including the two-face factor."""

    result = _calculate(
        fy_mpa=447.0,
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


def test_asce_2002_prism_example_is_reproduced() -> None:
    """Reproduce Dhakal-Maekawa Table 2/Table 3 specimen 45."""

    result = _calculate(
        fy_mpa=355.0,
        longitudinal_bar_diameter_mm=12.7,
        tie_bar_diameter_mm=sqrt(4.0 * 31.7 / pi),
        tie_spacing_mm=100.0,
        effective_tie_leg_length_mm=160.0,
        effective_tie_legs=2,
        restrained_longitudinal_bars=3,
        buckling_restraint_case="pure_compression",
    )

    assert result.effective_restrained_bars == 6
    assert result.equivalent_stiffness_ratio == pytest.approx(1.126, abs=0.002)
    assert result.buckling_intervals == 1


def test_asce_2002_flexural_column_example_is_reproduced() -> None:
    """Reproduce Dhakal-Maekawa Table 2/Table 3 specimen 42."""

    result = _calculate(
        fy_mpa=424.0,
        longitudinal_bar_diameter_mm=34.9,
        tie_bar_diameter_mm=sqrt(4.0 * 286.5 / pi),
        tie_spacing_mm=300.0,
        effective_tie_leg_length_mm=2196.0,
        effective_tie_legs=2,
        restrained_longitudinal_bars=19,
        buckling_restraint_case="bending",
    )

    assert result.equivalent_stiffness_ratio == pytest.approx(0.1015, abs=0.0001)
    assert result.buckling_intervals == 3


def test_pure_compression_doubles_effective_bars_and_reduces_kt() -> None:
    bending = _calculate(buckling_restraint_case="bending")
    compression = _calculate(buckling_restraint_case="pure_compression")

    assert bending.effective_restrained_bars == 2
    assert compression.effective_restrained_bars == 4
    assert compression.tie_stiffness_n_per_mm == pytest.approx(39269.9081699)
    assert compression.equivalent_stiffness_ratio == pytest.approx(
        0.5009286416
    )
    assert compression.buckling_intervals == 2


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
def test_shared_boundaries_select_the_conservative_higher_mode(
    keq: float,
    expected: int,
) -> None:
    assert select_buckling_intervals(keq) == expected


@pytest.mark.parametrize("invalid", [0.0, -0.1, nan, inf])
def test_interval_selection_rejects_nonpositive_or_nonfinite_values(
    invalid: float,
) -> None:
    with pytest.raises(ConfigError, match="finite number greater than zero"):
        select_buckling_intervals(invalid)


def test_interval_selection_rejects_values_below_table() -> None:
    with pytest.raises(ConfigError, match="minimum tabulated value 0.0009"):
        select_buckling_intervals(0.000899)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("fy_mpa", 0.0),
        ("elastic_modulus_mpa", inf),
        ("longitudinal_bar_diameter_mm", -1.0),
        ("tie_bar_diameter_mm", 0.0),
        ("tie_spacing_mm", nan),
        ("effective_tie_leg_length_mm", 0.0),
        ("tie_steel_modulus_mpa", -1.0),
    ],
)
def test_physical_calculator_rejects_invalid_scalar_inputs(
    key: str,
    value: float,
) -> None:
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
def test_physical_calculator_requires_positive_natural_counts(
    key: str,
    value: float,
) -> None:
    with pytest.raises(ConfigError, match="positive integer"):
        _calculate(**{key: value})


def test_physical_calculator_rejects_unsupported_restraint_case() -> None:
    with pytest.raises(ConfigError, match="bending, pure_compression"):
        _calculate(buckling_restraint_case="circular")


def test_more_transverse_stiffness_reduces_or_maintains_n() -> None:
    weaker = _calculate(tie_steel_modulus_mpa=100000.0)
    stronger = _calculate(tie_steel_modulus_mpa=200000.0)

    assert stronger.tie_stiffness_n_per_mm > weaker.tie_stiffness_n_per_mm
    assert stronger.equivalent_stiffness_ratio > weaker.equivalent_stiffness_ratio
    assert stronger.buckling_intervals <= weaker.buckling_intervals


def test_larger_legacy_n_increases_l_and_l_over_d() -> None:
    one = UnsupportedBucklingLengthCalculator.calculate_legacy(
        fy_mpa=420.0,
        elastic_modulus_mpa=200000.0,
        longitudinal_bar_diameter_mm=20.0,
        tie_spacing_mm=100.0,
        buckling_intervals=1,
    )
    two = UnsupportedBucklingLengthCalculator.calculate_legacy(
        fy_mpa=420.0,
        elastic_modulus_mpa=200000.0,
        longitudinal_bar_diameter_mm=20.0,
        tie_spacing_mm=100.0,
        buckling_intervals=2,
    )

    assert one.unsupported_length_mm == 100.0
    assert two.unsupported_length_mm == 200.0
    assert one.l_over_d == 5.0
    assert two.l_over_d == 10.0


def test_summary_and_curve_use_the_same_precalculated_result() -> None:
    model = RDM2019MonotonicCompressionModel(_physical_parameters())
    result = model.parameters.buckling_result
    summary = model.summary_parameters()
    curve = model.generate_curve(num_points=11)

    assert summary["epsilon_y"] == result.epsilon_y
    assert summary["equivalent_stiffness_ratio"] == result.equivalent_stiffness_ratio
    assert summary["buckling_intervals"] == result.buckling_intervals
    assert summary["L_over_D"] == result.l_over_d
    assert summary["rb"] == result.rb
    assert curve["summary"]["L_over_D"] == result.l_over_d
    assert curve["strain"][-1] == 0.10


def test_physical_and_legacy_inputs_cannot_be_mixed() -> None:
    with pytest.raises(ConfigError, match="cannot combine buckling_intervals"):
        _physical_parameters(buckling_intervals=1)
    with pytest.raises(ConfigError, match="epsilon_y is derived"):
        _physical_parameters(epsilon_y=0.0021)


def test_legacy_configuration_warns_and_remains_functional() -> None:
    with pytest.warns(DeprecationWarning, match="Legacy RDM geometry"):
        parameters = RDM2019Parameters(
            fy_mpa=420.0,
            fu_mpa=630.0,
            elastic_modulus_mpa=200000.0,
            epsilon_y=0.0021,
            epsilon_sh=0.01,
            epsilon_su=0.10,
            parameter_p=4.0,
            longitudinal_bar_diameter_mm=20.0,
            buckling_intervals=1,
            tie_spacing_mm=100.0,
            provenance=PROVENANCE,
        )

    assert parameters.resolved_unsupported_length_mm == 100.0
    assert parameters.resolved_l_over_d == 5.0
    assert parameters.buckling_result.equivalent_stiffness_ratio is None
    assert any(
        "Legacy RDM geometry" in warning
        for warning in parameters.buckling_result.applicability_warnings
    )


def test_legacy_json_mapping_is_supported_but_mixed_mapping_is_rejected() -> None:
    legacy_config = {
        "parameters": {
            "fy_MPa": 420.0,
            "fu_MPa": 630.0,
            "Es_MPa": 200000.0,
            "epsilon_y": 0.0021,
            "epsilon_sh": 0.01,
            "epsilon_su": 0.10,
            "parameter_p": 4.0,
            "longitudinal_bar_diameter_mm": 20.0,
            "buckling_intervals": 1,
            "tie_spacing_mm": 100.0,
        },
        "provenance": PROVENANCE.as_dict(),
    }
    with pytest.warns(DeprecationWarning, match="Legacy RDM geometry"):
        model = RDM2019MonotonicCompressionModel.from_config(legacy_config)

    assert model.parameters.resolved_l_over_d == 5.0
    assert model.summary_parameters()["buckling_calculation_mode"] == (
        "legacy_explicit_buckling_intervals"
    )

    mixed = {
        "parameters": {
            **legacy_config["parameters"],
            "tie_bar_diameter_mm": 10.0,
            "effective_tie_leg_length_mm": 200.0,
            "effective_tie_legs": 2,
            "restrained_longitudinal_bars": 2,
            "tie_steel_modulus_MPa": 200000.0,
            "buckling_restraint_case": "bending",
        },
        "provenance": PROVENANCE.as_dict(),
    }
    with pytest.raises(ConfigError, match="cannot be combined"):
        RDM2019MonotonicCompressionModel.from_config(mixed)

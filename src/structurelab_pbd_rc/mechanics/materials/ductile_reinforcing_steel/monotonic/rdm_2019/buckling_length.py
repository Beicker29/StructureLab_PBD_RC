"""Unsupported reinforcing-bar length from transverse-restraint stiffness."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Any

from structurelab_pbd_rc.core.exceptions import ConfigError


BUCKLING_RESTRAINT_CASES = ("bending", "pure_compression")
LEGACY_BUCKLING_WARNING = (
    "Legacy RDM geometry uses input buckling_intervals. Migrate to tie diameter, "
    "effective tie geometry, restrained bars, tie modulus and restraint case."
)


def _positive_float(value: Any, *, name: str) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be a finite number greater than zero.") from exc
    if not isfinite(resolved) or resolved <= 0.0:
        raise ConfigError(f"{name} must be a finite number greater than zero.")
    return resolved


def _positive_integer(value: Any, *, name: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{name} must be a positive integer.")
    try:
        resolved = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if not isfinite(resolved) or resolved <= 0.0 or not resolved.is_integer():
        raise ConfigError(f"{name} must be a positive integer.")
    return int(resolved)


def select_buckling_intervals(equivalent_stiffness_ratio: float) -> int:
    """Select the conservative tabulated buckling mode from ``keq = kt / k``.

    The definition follows Dhakal and Maekawa (2002), Table 1 and Table 3.
    User Bulletin 3 prints the inverse ratio on its first page, but uses
    ``kt / k`` in its later definition and in every worked example.
    """

    keq = _positive_float(
        equivalent_stiffness_ratio,
        name="equivalent_stiffness_ratio",
    )
    if keq > 0.7500:
        return 1
    if keq > 0.1649:
        return 2
    if keq > 0.0976:
        return 3
    if keq > 0.0448:
        return 4
    if keq > 0.0084:
        return 5
    if keq > 0.0063:
        return 6
    if keq > 0.0037:
        return 7
    if keq > 0.0031:
        return 8
    if keq > 0.0013:
        return 9
    if keq >= 0.0009:
        return 10
    raise ConfigError(
        "equivalent_stiffness_ratio is below the minimum tabulated value 0.0009."
    )


@dataclass(frozen=True)
class UnsupportedBucklingLengthResult:
    """Validated base-to-derived unsupported-length calculation."""

    epsilon_y: float
    tie_area_mm2: float | None
    longitudinal_bar_inertia_mm4: float
    reduced_flexural_rigidity_n_mm2: float
    effective_restrained_bars: int | None
    bar_normalized_stiffness_n_per_mm: float
    tie_stiffness_n_per_mm: float | None
    equivalent_stiffness_ratio: float | None
    buckling_intervals: int
    unsupported_length_mm: float
    l_over_d: float
    rb: float
    buckling_active: bool
    buckling_restraint_case: str
    calculation_mode: str
    applicability_warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return report keys with engineering-unit capitalization."""

        return {
            "epsilon_y": self.epsilon_y,
            "tie_area_mm2": self.tie_area_mm2,
            "longitudinal_bar_inertia_mm4": self.longitudinal_bar_inertia_mm4,
            "reduced_flexural_rigidity_N_mm2": (
                self.reduced_flexural_rigidity_n_mm2
            ),
            "effective_restrained_bars": self.effective_restrained_bars,
            "bar_normalized_stiffness_N_per_mm": (
                self.bar_normalized_stiffness_n_per_mm
            ),
            "tie_stiffness_N_per_mm": self.tie_stiffness_n_per_mm,
            "equivalent_stiffness_ratio": self.equivalent_stiffness_ratio,
            "buckling_intervals": self.buckling_intervals,
            "unsupported_length_mm": self.unsupported_length_mm,
            "L_over_D": self.l_over_d,
            "rb": self.rb,
            "buckling_active": self.buckling_active,
            "buckling_restraint_case": self.buckling_restraint_case,
            "buckling_calculation_mode": self.calculation_mode,
            "applicability_warnings": list(self.applicability_warnings),
        }


class UnsupportedBucklingLengthCalculator:
    """Calculate the unsupported length for rectangular transverse restraint."""

    @staticmethod
    def _common_values(
        *,
        fy_mpa: float,
        elastic_modulus_mpa: float,
        longitudinal_bar_diameter_mm: float,
        tie_spacing_mm: float,
    ) -> tuple[float, float, float, float]:
        fy = _positive_float(fy_mpa, name="fy_MPa")
        elastic_modulus = _positive_float(
            elastic_modulus_mpa,
            name="Es_MPa",
        )
        diameter = _positive_float(
            longitudinal_bar_diameter_mm,
            name="longitudinal_bar_diameter_mm",
        )
        spacing = _positive_float(tie_spacing_mm, name="tie_spacing_mm")
        epsilon_y = fy / elastic_modulus
        inertia = pi * diameter**4 / 64.0
        reduced_rigidity = (
            0.5 * elastic_modulus * inertia * sqrt(fy / 400.0)
        )
        bar_stiffness = pi**4 * reduced_rigidity / spacing**3
        if not isfinite(bar_stiffness) or bar_stiffness <= 0.0:
            raise ConfigError(
                "bar_normalized_stiffness_N_per_mm must be finite and positive."
            )
        return epsilon_y, inertia, reduced_rigidity, bar_stiffness

    @staticmethod
    def _applicability_warnings(
        *,
        fy_mpa: float,
        diameter_mm: float,
        rb: float,
    ) -> tuple[str, ...]:
        checks = (
            (
                200.0 < fy_mpa < 900.0,
                "fy is outside the reported 200 < fy < 900 MPa range.",
            ),
            (
                10.0 < diameter_mm < 36.0,
                "Bar diameter is outside the reported 10 < D < 36 mm range.",
            ),
            (
                8.0 < rb < 56.0,
                "rb is outside the reported 8 < rb < 56 range.",
            ),
        )
        return tuple(message for valid, message in checks if not valid)

    @classmethod
    def calculate(
        cls,
        *,
        fy_mpa: float,
        elastic_modulus_mpa: float,
        longitudinal_bar_diameter_mm: float,
        tie_bar_diameter_mm: float,
        tie_spacing_mm: float,
        effective_tie_leg_length_mm: float,
        effective_tie_legs: int,
        restrained_longitudinal_bars: int,
        tie_steel_modulus_mpa: float,
        buckling_restraint_case: str,
    ) -> UnsupportedBucklingLengthResult:
        """Calculate ``n``, ``L`` and ``L/D`` from physical base variables."""

        epsilon_y, inertia, reduced_rigidity, bar_stiffness = cls._common_values(
            fy_mpa=fy_mpa,
            elastic_modulus_mpa=elastic_modulus_mpa,
            longitudinal_bar_diameter_mm=longitudinal_bar_diameter_mm,
            tie_spacing_mm=tie_spacing_mm,
        )
        fy = float(fy_mpa)
        diameter = float(longitudinal_bar_diameter_mm)
        spacing = float(tie_spacing_mm)
        tie_diameter = _positive_float(
            tie_bar_diameter_mm,
            name="tie_bar_diameter_mm",
        )
        tie_leg_length = _positive_float(
            effective_tie_leg_length_mm,
            name="effective_tie_leg_length_mm",
        )
        tie_legs = _positive_integer(
            effective_tie_legs,
            name="effective_tie_legs",
        )
        restrained_bars = _positive_integer(
            restrained_longitudinal_bars,
            name="restrained_longitudinal_bars",
        )
        tie_modulus = _positive_float(
            tie_steel_modulus_mpa,
            name="tie_steel_modulus_MPa",
        )
        restraint_case = str(buckling_restraint_case).strip()
        if restraint_case not in BUCKLING_RESTRAINT_CASES:
            available = ", ".join(BUCKLING_RESTRAINT_CASES)
            raise ConfigError(
                f"buckling_restraint_case must be one of: {available}."
            )

        effective_bars = (
            restrained_bars
            if restraint_case == "bending"
            else 2 * restrained_bars
        )
        tie_area = pi * tie_diameter**2 / 4.0
        tie_stiffness = (
            tie_modulus
            * tie_area
            / tie_leg_length
            * tie_legs
            / effective_bars
        )
        if not isfinite(tie_stiffness) or tie_stiffness <= 0.0:
            raise ConfigError("tie_stiffness_N_per_mm must be finite and positive.")
        equivalent_ratio = tie_stiffness / bar_stiffness
        if not isfinite(equivalent_ratio) or equivalent_ratio <= 0.0:
            raise ConfigError(
                "equivalent_stiffness_ratio must be finite and positive."
            )
        intervals = select_buckling_intervals(equivalent_ratio)
        unsupported_length = intervals * spacing
        l_over_d = unsupported_length / diameter
        rb = l_over_d * sqrt(fy / 100.0)
        return UnsupportedBucklingLengthResult(
            epsilon_y=epsilon_y,
            tie_area_mm2=tie_area,
            longitudinal_bar_inertia_mm4=inertia,
            reduced_flexural_rigidity_n_mm2=reduced_rigidity,
            effective_restrained_bars=effective_bars,
            bar_normalized_stiffness_n_per_mm=bar_stiffness,
            tie_stiffness_n_per_mm=tie_stiffness,
            equivalent_stiffness_ratio=equivalent_ratio,
            buckling_intervals=intervals,
            unsupported_length_mm=unsupported_length,
            l_over_d=l_over_d,
            rb=rb,
            buckling_active=l_over_d >= 5.0,
            buckling_restraint_case=restraint_case,
            calculation_mode="rectangular_transverse_restraint",
            applicability_warnings=cls._applicability_warnings(
                fy_mpa=fy,
                diameter_mm=diameter,
                rb=rb,
            ),
        )

    @classmethod
    def calculate_legacy(
        cls,
        *,
        fy_mpa: float,
        elastic_modulus_mpa: float,
        longitudinal_bar_diameter_mm: float,
        tie_spacing_mm: float,
        buckling_intervals: int,
    ) -> UnsupportedBucklingLengthResult:
        """Resolve an old explicit-``n`` configuration without inventing restraint data."""

        epsilon_y, inertia, reduced_rigidity, bar_stiffness = cls._common_values(
            fy_mpa=fy_mpa,
            elastic_modulus_mpa=elastic_modulus_mpa,
            longitudinal_bar_diameter_mm=longitudinal_bar_diameter_mm,
            tie_spacing_mm=tie_spacing_mm,
        )
        intervals = _positive_integer(
            buckling_intervals,
            name="buckling_intervals",
        )
        fy = float(fy_mpa)
        diameter = float(longitudinal_bar_diameter_mm)
        spacing = float(tie_spacing_mm)
        unsupported_length = intervals * spacing
        l_over_d = unsupported_length / diameter
        rb = l_over_d * sqrt(fy / 100.0)
        warnings = (
            LEGACY_BUCKLING_WARNING,
            *cls._applicability_warnings(
                fy_mpa=fy,
                diameter_mm=diameter,
                rb=rb,
            ),
        )
        return UnsupportedBucklingLengthResult(
            epsilon_y=epsilon_y,
            tie_area_mm2=None,
            longitudinal_bar_inertia_mm4=inertia,
            reduced_flexural_rigidity_n_mm2=reduced_rigidity,
            effective_restrained_bars=None,
            bar_normalized_stiffness_n_per_mm=bar_stiffness,
            tie_stiffness_n_per_mm=None,
            equivalent_stiffness_ratio=None,
            buckling_intervals=intervals,
            unsupported_length_mm=unsupported_length,
            l_over_d=l_over_d,
            rb=rb,
            buckling_active=l_over_d >= 5.0,
            buckling_restraint_case="legacy_explicit_intervals",
            calculation_mode="legacy_explicit_buckling_intervals",
            applicability_warnings=warnings,
        )

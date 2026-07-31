"""Confinement geometry from Mander, Priestley and Park (1988)."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.common import required_float


@dataclass(frozen=True)
class ManderConfinementResult:
    """Resolved confinement quantities used by the constitutive equation."""

    section_type: str
    transverse_reinforcement: str
    core_area_mm2: float
    transverse_bar_area_mm2: float
    clear_tie_spacing_mm: float
    rho_cc: float
    rho_s: float
    k_e: float
    f_l_mpa: float
    rho_x: float | None = None
    rho_y: float | None = None
    f_lx_mpa: float | None = None
    f_ly_mpa: float | None = None
    sum_wi_squared_mm2: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable calculated-parameter mapping."""

        return {
            "section_type": self.section_type,
            "transverse_reinforcement": self.transverse_reinforcement,
            "core_area_mm2": self.core_area_mm2,
            "transverse_bar_area_mm2": self.transverse_bar_area_mm2,
            "clear_tie_spacing_mm": self.clear_tie_spacing_mm,
            "rho_cc": self.rho_cc,
            "rho_s": self.rho_s,
            "rho_x": self.rho_x,
            "rho_y": self.rho_y,
            "sum_wi_squared_mm2": self.sum_wi_squared_mm2,
            "k_e": self.k_e,
            "f_lx_mpa": self.f_lx_mpa,
            "f_ly_mpa": self.f_ly_mpa,
            "f_l_mpa": self.f_l_mpa,
        }


def _positive_integer(
    mapping: Mapping[str, Any],
    key: str,
    *,
    context: str,
) -> int:
    value = mapping.get(key)
    if isinstance(value, bool):
        raise ConfigError(f"{context}.{key} must be a positive integer.")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{context}.{key} must be a positive integer.") from exc
    if integer <= 0 or integer != float(value):
        raise ConfigError(f"{context}.{key} must be a positive integer.")
    return integer


def _common_geometry_values(
    geometry: Mapping[str, Any],
) -> tuple[float, float, float, float]:
    context = "parameters.geometry"
    tie_diameter = required_float(
        geometry,
        "tie_bar_diameter_mm",
        context=context,
    )
    tie_spacing = required_float(
        geometry,
        "tie_spacing_mm",
        context=context,
    )
    longitudinal_area = required_float(
        geometry,
        "longitudinal_steel_area_mm2",
        context=context,
    )
    if tie_diameter <= 0.0 or tie_spacing <= 0.0:
        raise ConfigError("Tie diameter and spacing must be positive.")
    if tie_spacing < tie_diameter:
        raise ConfigError(
            "parameters.geometry.tie_spacing_mm cannot be smaller than "
            "tie_bar_diameter_mm."
        )
    if longitudinal_area < 0.0:
        raise ConfigError(
            "parameters.geometry.longitudinal_steel_area_mm2 cannot be negative."
        )
    tie_area = pi * tie_diameter**2 / 4.0
    return tie_diameter, tie_spacing, longitudinal_area, tie_area


def _validate_effectiveness(k_e: float, *, section_type: str) -> None:
    if not isfinite(k_e) or not 0.0 < k_e <= 1.0:
        raise ConfigError(
            f"{section_type} confinement geometry produces k_e={k_e!r}; "
            "Mander effectiveness must satisfy 0 < k_e <= 1 and is not capped "
            "silently."
        )


def calculate_rectangular_confinement(
    geometry: Mapping[str, Any],
    *,
    f_yh_mpa: float,
) -> ManderConfinementResult:
    """Calculate rectangular-hoop confinement from Eqs. (21)-(28)."""

    context = "parameters.geometry"
    required_keys = (
        "core_width_mm",
        "core_depth_mm",
        "tie_bar_diameter_mm",
        "tie_spacing_mm",
        "transverse_legs_x",
        "transverse_legs_y",
        "longitudinal_steel_area_mm2",
        "clear_spacing_wi_mm",
    )
    require_keys(geometry, required_keys, context=context)
    core_width = required_float(geometry, "core_width_mm", context=context)
    core_depth = required_float(geometry, "core_depth_mm", context=context)
    if core_width <= 0.0 or core_depth <= 0.0:
        raise ConfigError("Rectangular core dimensions must be positive.")
    tie_diameter, tie_spacing, longitudinal_area, tie_area = (
        _common_geometry_values(geometry)
    )
    clear_spacing = tie_spacing - tie_diameter
    legs_x = _positive_integer(geometry, "transverse_legs_x", context=context)
    legs_y = _positive_integer(geometry, "transverse_legs_y", context=context)
    raw_wi = geometry["clear_spacing_wi_mm"]
    if not isinstance(raw_wi, list) or not raw_wi:
        raise ConfigError(
            "parameters.geometry.clear_spacing_wi_mm must be a non-empty list."
        )
    try:
        wi_values = [float(value) for value in raw_wi]
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            "parameters.geometry.clear_spacing_wi_mm must contain numbers."
        ) from exc
    if not all(isfinite(value) and value >= 0.0 for value in wi_values):
        raise ConfigError(
            "parameters.geometry.clear_spacing_wi_mm values must be finite "
            "and nonnegative."
        )

    core_area = core_width * core_depth
    rho_cc = longitudinal_area / core_area
    if not 0.0 <= rho_cc < 1.0:
        raise ConfigError(
            "Rectangular longitudinal reinforcement ratio must satisfy "
            "0 <= rho_cc < 1."
        )
    sum_wi_squared = sum(value**2 for value in wi_values)
    in_plane_factor = 1.0 - sum_wi_squared / (
        6.0 * core_width * core_depth
    )
    vertical_width_factor = 1.0 - clear_spacing / (2.0 * core_width)
    vertical_depth_factor = 1.0 - clear_spacing / (2.0 * core_depth)
    if min(in_plane_factor, vertical_width_factor, vertical_depth_factor) <= 0.0:
        raise ConfigError(
            "Rectangular geometry produces a nonpositive effectively confined "
            "area."
        )
    k_e = (
        in_plane_factor
        * vertical_width_factor
        * vertical_depth_factor
        / (1.0 - rho_cc)
    )
    _validate_effectiveness(k_e, section_type="Rectangular")

    transverse_area_x = legs_x * tie_area
    transverse_area_y = legs_y * tie_area
    rho_x = transverse_area_x / (core_depth * tie_spacing)
    rho_y = transverse_area_y / (core_width * tie_spacing)
    rho_s = rho_x + rho_y
    f_lx = k_e * rho_x * f_yh_mpa
    f_ly = k_e * rho_y * f_yh_mpa
    return ManderConfinementResult(
        section_type="rectangular",
        transverse_reinforcement="rectangular_hoops",
        core_area_mm2=core_area,
        transverse_bar_area_mm2=tie_area,
        clear_tie_spacing_mm=clear_spacing,
        rho_cc=rho_cc,
        rho_s=rho_s,
        k_e=k_e,
        f_l_mpa=0.5 * k_e * rho_s * f_yh_mpa,
        rho_x=rho_x,
        rho_y=rho_y,
        f_lx_mpa=f_lx,
        f_ly_mpa=f_ly,
        sum_wi_squared_mm2=sum_wi_squared,
    )


def calculate_circular_confinement(
    geometry: Mapping[str, Any],
    *,
    f_yh_mpa: float,
) -> ManderConfinementResult:
    """Calculate circular hoop or spiral confinement from Eqs. (12)-(19)."""

    context = "parameters.geometry"
    require_keys(
        geometry,
        (
            "core_diameter_mm",
            "tie_bar_diameter_mm",
            "tie_spacing_mm",
            "longitudinal_steel_area_mm2",
            "transverse_reinforcement",
        ),
        context=context,
    )
    core_diameter = required_float(
        geometry,
        "core_diameter_mm",
        context=context,
    )
    if core_diameter <= 0.0:
        raise ConfigError("Circular core diameter must be positive.")
    tie_diameter, tie_spacing, longitudinal_area, tie_area = (
        _common_geometry_values(geometry)
    )
    clear_spacing = tie_spacing - tie_diameter
    reinforcement = str(geometry["transverse_reinforcement"]).strip()
    if reinforcement not in {"circular_hoops", "spiral"}:
        raise ConfigError(
            "parameters.geometry.transverse_reinforcement must be "
            "'circular_hoops' or 'spiral'."
        )

    core_area = pi * core_diameter**2 / 4.0
    rho_cc = longitudinal_area / core_area
    if not 0.0 <= rho_cc < 1.0:
        raise ConfigError(
            "Circular longitudinal reinforcement ratio must satisfy "
            "0 <= rho_cc < 1."
        )
    arching_factor = 1.0 - clear_spacing / (2.0 * core_diameter)
    if arching_factor <= 0.0:
        raise ConfigError(
            "Circular geometry produces a nonpositive effectively confined area."
        )
    exponent = 2 if reinforcement == "circular_hoops" else 1
    k_e = arching_factor**exponent / (1.0 - rho_cc)
    _validate_effectiveness(k_e, section_type="Circular")

    rho_s = 4.0 * tie_area / (core_diameter * tie_spacing)
    f_l = 0.5 * k_e * rho_s * f_yh_mpa
    return ManderConfinementResult(
        section_type="circular",
        transverse_reinforcement=reinforcement,
        core_area_mm2=core_area,
        transverse_bar_area_mm2=tie_area,
        clear_tie_spacing_mm=clear_spacing,
        rho_cc=rho_cc,
        rho_s=rho_s,
        k_e=k_e,
        f_l_mpa=f_l,
        f_lx_mpa=f_l,
        f_ly_mpa=f_l,
    )


def calculate_confinement(
    geometry: Mapping[str, Any],
    *,
    f_yh_mpa: float,
) -> ManderConfinementResult:
    """Dispatch confinement calculations by explicitly configured section type."""

    require_keys(geometry, ("section_type",), context="parameters.geometry")
    section_type = str(geometry["section_type"]).strip()
    if section_type == "rectangular":
        return calculate_rectangular_confinement(
            geometry,
            f_yh_mpa=f_yh_mpa,
        )
    if section_type == "circular":
        return calculate_circular_confinement(
            geometry,
            f_yh_mpa=f_yh_mpa,
        )
    raise ConfigError(
        "parameters.geometry.section_type must be 'rectangular' or 'circular'."
    )

"""Confinement geometry and parameter calculations."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.mechanics.geometry.confined_core import ConfinedCore
from structurelab_pbd_rc.mechanics.geometry.transverse_reinforcement import TransverseReinforcement
from structurelab_pbd_rc.mechanics.materials.concrete.equations import effective_confinement_pressure


@dataclass(frozen=True)
class RectangularConfinementGeometry:
    """Geometry needed for rectangular tie confinement calculations."""

    core_width_cm: float
    core_height_cm: float
    tie_spacing_cm: float
    tie_bar_diameter_mm: float
    longitudinal_steel_area_cm2: float = 0.0
    longitudinal_bars_per_side: int = 5
    clear_spacing_wi_cm: tuple[float, ...] | None = None

    @classmethod
    def from_core(
        cls,
        core: ConfinedCore,
        transverse_reinforcement: TransverseReinforcement,
        *,
        longitudinal_steel_area_cm2: float,
        longitudinal_bars_per_side: int = 5,
        clear_spacing_wi_cm: tuple[float, ...] | None = None,
    ) -> "RectangularConfinementGeometry":
        """Build confinement geometry from project geometry objects."""

        return cls(
            core_width_cm=core.width_cm,
            core_height_cm=core.height_cm,
            tie_spacing_cm=transverse_reinforcement.spacing_cm,
            tie_bar_diameter_mm=transverse_reinforcement.effective_diameter_mm,
            longitudinal_steel_area_cm2=longitudinal_steel_area_cm2,
            longitudinal_bars_per_side=longitudinal_bars_per_side,
            clear_spacing_wi_cm=clear_spacing_wi_cm,
        )


@dataclass(frozen=True)
class ConfinementParameters:
    """Calculated rectangular confinement parameters."""

    rho_x: float
    rho_y: float
    rho_s: float
    rho_cc: float
    ke: float
    fl_eff_mpa: float
    transverse_yield_strength_mpa: float
    clear_tie_spacing_cm: float
    wi_x_cm: float
    wi_y_cm: float
    wi_cm: list[float]
    sum_wi2_cm2: float
    assumptions: list[str]

    def as_dict(self) -> dict[str, object]:
        """Return a serializable summary."""

        return {
            "rho_x": self.rho_x,
            "rho_y": self.rho_y,
            "rho_s": self.rho_s,
            "rho_cc": self.rho_cc,
            "ke": self.ke,
            "fl_eff_mpa": self.fl_eff_mpa,
            "transverse_yield_strength_mpa": self.transverse_yield_strength_mpa,
            "clear_tie_spacing_cm": self.clear_tie_spacing_cm,
            "wi_x_cm": self.wi_x_cm,
            "wi_y_cm": self.wi_y_cm,
            "wi_cm": self.wi_cm,
            "sum_wi2_cm2": self.sum_wi2_cm2,
            "assumptions": self.assumptions,
        }


def calculate_rectangular_confinement_effectiveness(
    geometry: RectangularConfinementGeometry,
) -> float:
    """Return the confinement effectiveness factor.

    Implements the rectangular-tie structure from the Etapa 1 PDF using the
    project convention for symmetric perimeter bars. The `wi` spacings are
    inferred from the configured number of longitudinal bars per side.
    """

    return calculate_rectangular_confinement_parameters(
        geometry,
        transverse_area_x_mm2=0.0,
        transverse_area_y_mm2=0.0,
        transverse_yield_strength_mpa=0.0,
    ).ke


def calculate_rectangular_confinement_parameters(
    geometry: RectangularConfinementGeometry,
    *,
    transverse_area_x_mm2: float,
    transverse_area_y_mm2: float,
    transverse_yield_strength_mpa: float,
) -> ConfinementParameters:
    """Calculate rectangular confinement parameters for Mander-style models."""

    core_width_mm = geometry.core_width_cm * 10.0
    core_height_mm = geometry.core_height_cm * 10.0
    spacing_mm = geometry.tie_spacing_cm * 10.0

    rho_x = transverse_area_x_mm2 / (core_height_mm * spacing_mm) if transverse_area_x_mm2 else 0.0
    rho_y = transverse_area_y_mm2 / (core_width_mm * spacing_mm) if transverse_area_y_mm2 else 0.0
    rho_s = rho_x + rho_y

    core_area_cm2 = geometry.core_width_cm * geometry.core_height_cm
    rho_cc = geometry.longitudinal_steel_area_cm2 / core_area_cm2 if core_area_cm2 else 0.0

    spaces_per_side = max(geometry.longitudinal_bars_per_side - 1, 1)
    inferred_wi_x_cm = geometry.core_width_cm / spaces_per_side
    inferred_wi_y_cm = geometry.core_height_cm / spaces_per_side
    if geometry.clear_spacing_wi_cm:
        wi_cm = list(geometry.clear_spacing_wi_cm)
        wi_x_cm = inferred_wi_x_cm
        wi_y_cm = inferred_wi_y_cm
        sum_wi2_cm2 = sum(wi**2 for wi in wi_cm)
    else:
        wi_x_cm = inferred_wi_x_cm
        wi_y_cm = inferred_wi_y_cm
        wi_cm = [wi_x_cm] * (2 * spaces_per_side) + [wi_y_cm] * (2 * spaces_per_side)
        sum_wi2_cm2 = sum(wi**2 for wi in wi_cm)

    tie_diameter_cm = geometry.tie_bar_diameter_mm / 10.0
    clear_tie_spacing_cm = max(geometry.tie_spacing_cm - tie_diameter_cm, 0.0)

    in_plane_factor = max(1.0 - sum_wi2_cm2 / (6.0 * geometry.core_width_cm * geometry.core_height_cm), 0.0)
    spacing_factor_x = max(1.0 - clear_tie_spacing_cm / (2.0 * geometry.core_width_cm), 0.0)
    spacing_factor_y = max(1.0 - clear_tie_spacing_cm / (2.0 * geometry.core_height_cm), 0.0)
    denominator = max(1.0 - rho_cc, 1e-9)
    ke = max(min(in_plane_factor * spacing_factor_x * spacing_factor_y / denominator, 1.0), 0.0)
    fl_eff_mpa = effective_confinement_pressure(ke=ke, rho_s=rho_s, fyh=transverse_yield_strength_mpa)

    assumptions = [
        "Core dimensions are measured to the tie centerline unless YAML states otherwise.",
        "wi spacing is read from YAML when provided; otherwise it is inferred from a symmetric perimeter layout.",
        "Effective transverse areas use configured tie legs in x and y directions.",
    ]
    return ConfinementParameters(
        rho_x=rho_x,
        rho_y=rho_y,
        rho_s=rho_s,
        rho_cc=rho_cc,
        ke=ke,
        fl_eff_mpa=fl_eff_mpa,
        transverse_yield_strength_mpa=transverse_yield_strength_mpa,
        clear_tie_spacing_cm=clear_tie_spacing_cm,
        wi_x_cm=wi_x_cm,
        wi_y_cm=wi_y_cm,
        wi_cm=wi_cm,
        sum_wi2_cm2=sum_wi2_cm2,
        assumptions=assumptions,
    )


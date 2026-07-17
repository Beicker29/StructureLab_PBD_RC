"""Confined core geometry interfaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfinedCore:
    """Approximate confined core dimensions in centimeters."""

    width_cm: float
    height_cm: float
    boundary: str = "tie_centerline"

    @property
    def width_mm(self) -> float:
        """Return core width in millimeters."""

        return self.width_cm * 10.0

    @property
    def height_mm(self) -> float:
        """Return core height in millimeters."""

        return self.height_cm * 10.0

    @property
    def area_cm2(self) -> float:
        """Return confined core area in square centimeters."""

        return self.width_cm * self.height_cm

    def as_dict(self) -> dict[str, object]:
        """Return a serializable summary."""

        return {
            "width_cm": self.width_cm,
            "height_cm": self.height_cm,
            "area_cm2": self.area_cm2,
            "boundary": self.boundary,
        }

def derive_confined_core_from_cover(
    gross_width_cm: float,
    gross_height_cm: float,
    clear_cover_to_tie_cm: float,
    tie_bar_diameter_mm: float,
    boundary: str = "tie_centerline",
) -> ConfinedCore:
    """Derive confined core dimensions from cover.

    The Etapa 2 PDF gives clear cover to the tie but not every internal
    dimension. The default project assumption is a core measured to the tie
    centerline: gross dimension minus twice the clear cover and half a tie
    diameter at each side.
    """

    tie_diameter_cm = tie_bar_diameter_mm / 10.0
    if boundary == "tie_centerline":
        reduction_each_side_cm = clear_cover_to_tie_cm + 0.5 * tie_diameter_cm
    elif boundary == "tie_outer_face":
        reduction_each_side_cm = clear_cover_to_tie_cm
    elif boundary == "tie_inner_face":
        reduction_each_side_cm = clear_cover_to_tie_cm + tie_diameter_cm
    else:
        raise ValueError(f"Unknown confined core boundary convention: {boundary}")

    width_cm = gross_width_cm - 2.0 * reduction_each_side_cm
    height_cm = gross_height_cm - 2.0 * reduction_each_side_cm
    if width_cm <= 0 or height_cm <= 0:
        raise ValueError("Confined core dimensions must be positive.")
    return ConfinedCore(width_cm=width_cm, height_cm=height_cm, boundary=boundary)

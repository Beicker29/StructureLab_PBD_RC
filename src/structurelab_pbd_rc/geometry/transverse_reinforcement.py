"""Transverse reinforcement geometry interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.materials.library.rebar_database import get_rebar_properties


@dataclass(frozen=True)
class TransverseReinforcement:
    """Transverse reinforcement for confinement and buckling stability."""

    reinforcement_type: str
    bar_mark: str
    spacing_cm: float
    diameter_mm: float | None = None
    legs_x: int = 2
    legs_y: int = 2

    @property
    def bar_properties(self) -> dict[str, object]:
        """Return nominal tie bar properties."""

        return get_rebar_properties(self.bar_mark)

    @property
    def effective_diameter_mm(self) -> float:
        """Return configured or nominal tie diameter."""

        if self.diameter_mm is not None:
            return self.diameter_mm
        return float(self.bar_properties["diameter_mm"])

    @property
    def bar_area_mm2(self) -> float:
        """Return tie bar area in square millimeters."""

        return float(self.bar_properties["area_mm2"])

    @property
    def spacing_mm(self) -> float:
        """Return tie spacing in millimeters."""

        return self.spacing_cm * 10.0

    @property
    def area_x_mm2(self) -> float:
        """Return effective tie leg area for confinement in x direction."""

        return self.legs_x * self.bar_area_mm2

    @property
    def area_y_mm2(self) -> float:
        """Return effective tie leg area for confinement in y direction."""

        return self.legs_y * self.bar_area_mm2

    def as_dict(self) -> dict[str, object]:
        """Return a serializable summary."""

        return {
            "reinforcement_type": self.reinforcement_type,
            "bar_mark": self.bar_mark,
            "diameter_mm": self.effective_diameter_mm,
            "bar_area_mm2": self.bar_area_mm2,
            "spacing_cm": self.spacing_cm,
            "spacing_mm": self.spacing_mm,
            "legs_x": self.legs_x,
            "legs_y": self.legs_y,
            "area_x_mm2": self.area_x_mm2,
            "area_y_mm2": self.area_y_mm2,
        }

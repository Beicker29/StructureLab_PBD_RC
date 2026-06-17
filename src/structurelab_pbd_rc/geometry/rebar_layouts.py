"""Longitudinal reinforcement layout interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.materials.library.rebar_database import get_rebar_properties


@dataclass(frozen=True)
class RebarLayout:
    """Simplified longitudinal reinforcement layout."""

    bar_count: int
    bar_mark: str
    layout_description: str = "symmetrical perimeter layout"

    @property
    def bar_properties(self) -> dict[str, object]:
        """Return nominal properties from the internal rebar database."""

        return get_rebar_properties(self.bar_mark)

    @property
    def bar_diameter_mm(self) -> float:
        """Return longitudinal bar diameter in millimeters."""

        return float(self.bar_properties["diameter_mm"])

    @property
    def single_bar_area_mm2(self) -> float:
        """Return single bar area in square millimeters."""

        return float(self.bar_properties["area_mm2"])

    @property
    def total_area_mm2(self) -> float:
        """Return total longitudinal steel area in square millimeters."""

        return self.bar_count * self.single_bar_area_mm2

    @property
    def total_area_cm2(self) -> float:
        """Return total longitudinal steel area in square centimeters."""

        return self.total_area_mm2 / 100.0

    def longitudinal_ratio(self, gross_area_cm2: float) -> float:
        """Return longitudinal reinforcement ratio using gross area."""

        return self.total_area_cm2 / gross_area_cm2

    def as_dict(self, gross_area_cm2: float | None = None) -> dict[str, object]:
        """Return a serializable summary."""

        data: dict[str, object] = {
            "bar_count": self.bar_count,
            "bar_mark": self.bar_mark,
            "bar_diameter_mm": self.bar_diameter_mm,
            "single_bar_area_mm2": self.single_bar_area_mm2,
            "total_area_mm2": self.total_area_mm2,
            "total_area_cm2": self.total_area_cm2,
            "layout_description": self.layout_description,
        }
        if gross_area_cm2 is not None:
            data["longitudinal_ratio"] = self.longitudinal_ratio(gross_area_cm2)
        return data

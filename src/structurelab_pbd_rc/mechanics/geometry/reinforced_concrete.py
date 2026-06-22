"""Reinforced concrete section assembly interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.mechanics.geometry.rebar_layouts import RebarLayout
from structurelab_pbd_rc.mechanics.geometry.sections import RectangularSection
from structurelab_pbd_rc.mechanics.geometry.transverse_reinforcement import TransverseReinforcement


@dataclass(frozen=True)
class ReinforcedConcreteSection:
    """Container joining geometry with longitudinal and transverse steel."""

    gross_section: RectangularSection
    longitudinal_reinforcement: RebarLayout
    transverse_reinforcement: TransverseReinforcement
    clear_cover_to_tie_cm: float

    @property
    def gross_area_cm2(self) -> float:
        """Return gross concrete section area."""

        return self.gross_section.area_cm2

    @property
    def longitudinal_steel_area_cm2(self) -> float:
        """Return total longitudinal reinforcement area."""

        return self.longitudinal_reinforcement.total_area_cm2

    @property
    def longitudinal_ratio(self) -> float:
        """Return longitudinal reinforcement ratio."""

        return self.longitudinal_steel_area_cm2 / self.gross_area_cm2

    def as_dict(self) -> dict[str, object]:
        """Return a serializable summary."""

        return {
            "gross_section": self.gross_section.as_dict(),
            "longitudinal_reinforcement": self.longitudinal_reinforcement.as_dict(self.gross_area_cm2),
            "transverse_reinforcement": self.transverse_reinforcement.as_dict(),
            "clear_cover_to_tie_cm": self.clear_cover_to_tie_cm,
            "longitudinal_ratio": self.longitudinal_ratio,
        }


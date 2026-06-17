"""Basic section geometry objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RectangularSection:
    """Rectangular section dimensions in centimeters."""

    width_cm: float
    height_cm: float

    @property
    def area_cm2(self) -> float:
        """Return gross area in square centimeters."""

        return self.width_cm * self.height_cm

    @property
    def width_mm(self) -> float:
        """Return width in millimeters."""

        return self.width_cm * 10.0

    @property
    def height_mm(self) -> float:
        """Return height in millimeters."""

        return self.height_cm * 10.0

    def as_dict(self) -> dict[str, float]:
        """Return a serializable summary."""

        return {
            "width_cm": self.width_cm,
            "height_cm": self.height_cm,
            "area_cm2": self.area_cm2,
        }

"""Demand/capacity evaluation interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DemandCapacityRatio:
    """Simple demand/capacity result placeholder."""

    demand: float
    capacity: float

    @property
    def ratio(self) -> float:
        """Return demand divided by capacity."""

        return self.demand / self.capacity


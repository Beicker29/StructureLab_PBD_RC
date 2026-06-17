"""Element limit-state interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LimitState:
    """Named limit state placeholder."""

    name: str
    description: str


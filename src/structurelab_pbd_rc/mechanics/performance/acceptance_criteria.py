"""Acceptance criteria interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptanceCriterion:
    """Named acceptance criterion placeholder."""

    name: str
    limit_value: float


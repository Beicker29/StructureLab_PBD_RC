"""Beam element interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Beam:
    """Future reinforced concrete beam model."""

    name: str


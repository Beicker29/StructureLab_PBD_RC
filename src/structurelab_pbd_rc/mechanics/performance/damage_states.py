"""Damage state interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DamageState:
    """Named damage state placeholder."""

    name: str
    description: str


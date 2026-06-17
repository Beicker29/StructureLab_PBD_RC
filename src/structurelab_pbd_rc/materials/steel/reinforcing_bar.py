"""Reinforcing bar data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReinforcingBar:
    """Nominal reinforcing bar description."""

    mark: str
    diameter_mm: float
    area_mm2: float | None = None
    expected_yield_strength_mpa: float | None = None
    elastic_modulus_mpa: float = 200000.0


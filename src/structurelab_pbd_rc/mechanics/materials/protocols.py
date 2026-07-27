"""Shared strain-vector helpers for material characterization."""

from __future__ import annotations

from math import isfinite
from typing import Iterable

from structurelab_pbd_rc.core.exceptions import ConfigError


def linear_strain_vector(start: float, stop: float, count: int) -> list[float]:
    """Return an ordered strain vector including both endpoints."""

    if count < 2:
        raise ConfigError(f"strain point count must be at least 2. Received {count!r}.")
    if not isfinite(start) or not isfinite(stop):
        raise ConfigError("strain vector endpoints must be finite.")
    step = (stop - start) / (count - 1)
    values = [start + index * step for index in range(count)]
    values[0] = start
    values[-1] = stop
    return values


def validate_strain_history(values: Iterable[float], *, minimum_points: int = 2) -> list[float]:
    """Validate a sequential strain history without sorting or deduplicating it."""

    history = [float(value) for value in values]
    if len(history) < minimum_points:
        raise ConfigError(f"strain history must contain at least {minimum_points} points.")
    if not all(isfinite(value) for value in history):
        raise ConfigError("strain history values must be finite.")
    return history

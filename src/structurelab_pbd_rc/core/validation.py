"""Validation helpers for configurations and model inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from structurelab_pbd_rc.core.exceptions import ConfigError


def require_keys(mapping: Mapping[str, Any], required_keys: Sequence[str], *, context: str) -> None:
    """Raise ConfigError when required keys are missing."""

    missing = [key for key in required_keys if key not in mapping]
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(f"Missing required keys in {context}: {joined}")


def require_positive(value: float, *, name: str) -> None:
    """Raise ConfigError when a numeric value is not positive."""

    if value <= 0:
        raise ConfigError(f"{name} must be positive. Received {value!r}.")


def require_unit(actual: str, allowed_units: Sequence[str], *, name: str) -> None:
    """Raise ConfigError when a unit is not one of the allowed units."""

    if actual not in allowed_units:
        allowed = ", ".join(allowed_units)
        raise ConfigError(f"{name} unit must be one of [{allowed}]. Received {actual!r}.")


def require_value_with_unit(
    mapping: Mapping[str, Any],
    *,
    name: str,
    allowed_units: Sequence[str],
    positive: bool = True,
) -> None:
    """Validate a small `{value, unit}` mapping from YAML."""

    require_keys(mapping, ["value", "unit"], context=name)
    if positive:
        require_positive(float(mapping["value"]), name=f"{name}.value")
    require_unit(str(mapping["unit"]), allowed_units, name=name)

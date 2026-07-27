"""Shared contracts for material-model inputs and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys


def required_float(mapping: Mapping[str, Any], key: str, *, context: str) -> float:
    """Read one required finite float from a configuration mapping."""

    require_keys(mapping, (key,), context=context)
    value = mapping[key]
    if value is None:
        raise ConfigError(f"{context}.{key} must be provided explicitly.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{context}.{key} must be numeric. Received {value!r}.") from exc
    if not isfinite(number):
        raise ConfigError(f"{context}.{key} must be finite. Received {value!r}.")
    return number


def optional_float(mapping: Mapping[str, Any], key: str, *, context: str) -> float | None:
    """Read one optional finite float from a configuration mapping."""

    value = mapping.get(key)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{context}.{key} must be numeric or null. Received {value!r}.") from exc
    if not isfinite(number):
        raise ConfigError(f"{context}.{key} must be finite. Received {value!r}.")
    return number


@dataclass(frozen=True)
class MaterialProvenance:
    """Source and calibration metadata carried into every response."""

    source: str
    citation: str
    source_location: str
    specimen_or_profile: str
    calibration_status: str

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "MaterialProvenance":
        """Build provenance metadata from explicit configuration fields."""

        required = ("source", "citation", "source_location", "specimen_or_profile", "calibration_status")
        require_keys(mapping, required, context="provenance")
        values = {
            key: "" if mapping[key] is None else str(mapping[key]).strip()
            for key in required
        }
        empty = [key for key, value in values.items() if not value]
        if empty:
            raise ConfigError(f"provenance fields cannot be empty: {', '.join(empty)}")
        return cls(**values)

    def as_dict(self) -> dict[str, str]:
        """Return JSON-safe metadata."""

        return {
            "source": self.source,
            "citation": self.citation,
            "source_location": self.source_location,
            "specimen_or_profile": self.specimen_or_profile,
            "calibration_status": self.calibration_status,
        }


@dataclass(frozen=True)
class UniaxialResponse:
    """Common stress, tangent and diagnostic response."""

    strain: float
    stress_mpa: float
    tangent_mpa: float
    branch: str
    loading_direction: str
    in_domain: bool
    failed: bool = False
    reversal: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable response mapping."""

        return {
            "strain": self.strain,
            "stress_mpa": self.stress_mpa,
            "tangent_mpa": self.tangent_mpa,
            "branch": self.branch,
            "loading_direction": self.loading_direction,
            "in_domain": self.in_domain,
            "failed": self.failed,
            "reversal": self.reversal,
            "diagnostics": dict(self.diagnostics),
            "warnings": list(self.warnings),
        }

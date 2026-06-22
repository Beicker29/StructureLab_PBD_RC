"""Nominal rebar properties used by the starter configurations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from structurelab_pbd_rc.core.exceptions import ConfigError


@dataclass(frozen=True)
class RebarProperties:
    """Nominal reinforcing bar properties."""

    designation: str
    name: str
    diameter_mm: float
    area_mm2: float

    def as_dict(self) -> dict[str, Any]:
        """Return properties as a serializable dictionary."""

        return {
            "designation": self.designation,
            "name": self.name,
            "diameter_mm": self.diameter_mm,
            "area_mm2": self.area_mm2,
        }


REBAR_DATABASE: dict[str, dict[str, Any]] = {
    "#4": RebarProperties(
        designation="#4",
        name="No. 4 reinforcing bar",
        diameter_mm=12.7,
        area_mm2=129.0,
    ).as_dict(),
    "#7": RebarProperties(
        designation="#7",
        name="No. 7 reinforcing bar",
        diameter_mm=22.2,
        area_mm2=387.0,
    ).as_dict(),
}


def get_rebar_properties(mark: str) -> dict[str, Any]:
    """Return a copy of nominal rebar properties."""

    try:
        return deepcopy(REBAR_DATABASE[mark])
    except KeyError as exc:
        available = ", ".join(sorted(REBAR_DATABASE))
        raise ConfigError(f"Unknown rebar designation {mark!r}. Available: {available}") from exc


def rebar_exists(mark: str) -> bool:
    """Return True when a bar designation exists in the internal database."""

    return mark in REBAR_DATABASE

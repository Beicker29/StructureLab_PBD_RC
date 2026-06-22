"""Welded wire mesh properties summarized from the Taller 1 PDF."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


WELDED_WIRE_MESH_DATABASE: dict[int, dict[str, Any]] = {
    4: {"fy_mpa": 612.0, "fu_mpa": 689.0, "epsilon_u": 0.0124},
    5: {"fy_mpa": 610.0, "fu_mpa": 681.0, "epsilon_u": 0.0113},
    6: {"fy_mpa": 641.0, "fu_mpa": 691.0, "epsilon_u": 0.0095},
}


def get_mesh_properties(diameter_mm: int) -> dict[str, Any]:
    """Return a copy of welded wire mesh properties by diameter."""

    return deepcopy(WELDED_WIRE_MESH_DATABASE[diameter_mm])


def mesh_diameter_exists(diameter_mm: int) -> bool:
    """Return True when a mesh diameter is available."""

    return diameter_mm in WELDED_WIRE_MESH_DATABASE

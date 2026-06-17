"""Unit helpers.

This module intentionally stays light in the scaffold. A full unit system can
be added later if the workshops need dimensional analysis or automatic
conversion tracking.
"""


def centimeters_to_meters(value_cm: float) -> float:
    """Convert centimeters to meters."""

    return value_cm / 100.0


def millimeters_to_meters(value_mm: float) -> float:
    """Convert millimeters to meters."""

    return value_mm / 1000.0


def mpa_to_kpa(value_mpa: float) -> float:
    """Convert MPa to kPa."""

    return value_mpa * 1000.0


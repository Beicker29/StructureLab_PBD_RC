"""Small helpers for stress-strain curves."""

from __future__ import annotations


def linspace(start: float, stop: float, count: int) -> list[float]:
    """Return evenly spaced values including start and stop."""

    if count < 2:
        return [start]
    step = (stop - start) / (count - 1)
    return [start + i * step for i in range(count)]


def trapezoid_area(x_values: list[float], y_values: list[float]) -> float:
    """Return area under a curve using the trapezoidal rule."""

    area = 0.0
    for index in range(1, min(len(x_values), len(y_values))):
        dx = x_values[index] - x_values[index - 1]
        avg_y = 0.5 * (y_values[index] + y_values[index - 1])
        area += dx * avg_y
    return area


def curve_rows(curves: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Flatten named curves into rows suitable for CSV export."""

    rows: list[dict[str, object]] = []
    for model_name, curve in curves.items():
        strains = curve.get("strain", [])
        stresses = curve.get("stress", [])
        for strain, stress in zip(strains, stresses):
            rows.append(
                {
                    "model": model_name,
                    "strain": strain,
                    "stress_mpa": stress,
                }
            )
    return rows

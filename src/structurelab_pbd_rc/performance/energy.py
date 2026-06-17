"""Energy metrics for material curves."""

from structurelab_pbd_rc.core.curves import trapezoid_area


def calculate_toughness(strain: list[float], stress: list[float]) -> float:
    """Return area under a stress-strain curve."""

    return trapezoid_area(strain, stress)


def calculate_energy_metrics(curves: dict[str, dict[str, object]]) -> dict[str, dict[str, float]]:
    """Calculate toughness and relative energy for named curves."""

    raw: dict[str, float] = {}
    for name, curve in curves.items():
        raw[name] = calculate_toughness(
            list(curve.get("strain", [])),
            list(curve.get("stress", [])),
        )
    reference = max(raw.values()) if raw else 0.0
    return {
        name: {
            "toughness_mpa": value,
            "relative_energy": value / reference if reference else 0.0,
        }
        for name, value in raw.items()
    }

"""Table reporting helpers."""

from __future__ import annotations

from structurelab_pbd_rc.performance.ductility import calculate_curve_metrics_table


def build_material_parameter_table(curves: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Build a flat table of model parameter values."""

    rows: list[dict[str, object]] = []
    for model_name, curve in curves.items():
        parameters = curve.get("parameters", {})
        if isinstance(parameters, dict):
            for key, value in parameters.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    rows.append({"model": model_name, "parameter": key, "value": value})
    return rows


def build_curve_metrics_table(curves: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Build comparative curve metrics."""

    return calculate_curve_metrics_table(curves)


def build_assumptions_table(assumptions: list[str]) -> list[dict[str, object]]:
    """Build assumptions table rows."""

    return [{"index": index + 1, "assumption": assumption} for index, assumption in enumerate(assumptions)]

"""Reusable helpers for model reports and figure labels."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CONSTITUTIVE_MODEL_REPORT_KEYS = (
    "mander_classic_unconfined_concrete",
    "mander_classic_confined_concrete",
    "mander_adjusted_confined_concrete",
    "attard_setunge_unconfined_concrete",
    "attard_setunge_confined_concrete",
    "steel_tension_mander",
    "steel_compression_no_buckling",
    "steel_compression_with_buckling",
    "welded_wire_mesh",
)

CONFINED_CONCRETE_MODEL_KEYS = {
    "mander_classic_confined_concrete",
    "mander_adjusted_confined_concrete",
    "attard_setunge_confined_concrete",
}

MODEL_ALIASES = {
    "unconfined_concrete": "mander_classic_unconfined_concrete",
    "mander_classic": "mander_classic_confined_concrete",
    "mander_adjusted": "mander_adjusted_confined_concrete",
    "attard_setunge_unconfined": "attard_setunge_unconfined_concrete",
    "attard_setunge_confined": "attard_setunge_confined_concrete",
    "steel_tension": "steel_tension_mander",
}

MODEL_LABELS = {
    "mander_classic_unconfined_concrete": "Mander clásico no confinado",
    "mander_classic_confined_concrete": "Mander clásico confinado",
    "mander_adjusted_confined_concrete": "Mander ajustado confinado",
    "attard_setunge_unconfined_concrete": "Attard-Setunge no confinado",
    "attard_setunge_confined_concrete": "Attard-Setunge confinado",
    "steel_tension_mander": "Acero longitudinal en tracción",
    "steel_compression_no_buckling": "Acero en compresión sin pandeo",
    "steel_compression_with_buckling": "Acero en compresión con pandeo",
    "welded_wire_mesh": "Malla electrosoldada",
}


def canonical_model_key(model_key: str) -> str:
    """Return the canonical report key for a model name."""

    return MODEL_ALIASES.get(model_key, model_key)


def unit_label(unit: str) -> str:
    """Return report units enclosed in brackets."""

    normalized = "mm/mm" if unit in {"m/m", "mm/mm"} else unit
    if normalized.startswith("[") and normalized.endswith("]"):
        return normalized
    return f"[{normalized}]"


def report_value(value: object, unit: str = "-") -> dict[str, object]:
    """Return a report value with standard unit formatting."""

    return {"value": value, "unit": unit_label(unit)}


def report_equation(
    equation: str,
    value: object,
    unit: str = "-",
    variables: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return an equation, evaluated value and optional variables."""

    item = {"equation": equation, "value": value, "unit": unit_label(unit)}
    if variables:
        item["variables"] = variables
    return item


def report_section(
    title: str,
    description: str,
    parameters: dict[str, object],
    *,
    inputs_used: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return a readable YAML report section."""

    section: dict[str, object] = {"title": title, "description": description}
    if inputs_used:
        section["inputs_used"] = inputs_used
    section["parameters"] = parameters
    return section


def model_plot_text(model_key: str) -> dict[str, str]:
    """Return titles and axes for individual model figures."""

    canonical_key = canonical_model_key(model_key)
    if canonical_key == "mander_classic_unconfined_concrete":
        xlabel = "Deformación unitaria, εc [mm/mm]"
        ylabel = "Esfuerzo, fc [MPa]"
    elif canonical_key.startswith("steel_compression"):
        xlabel = "Deformación unitaria de compresión, εs [mm/mm]"
        ylabel = "Esfuerzo de compresión, fs [MPa]"
    elif canonical_key in {"steel_tension_mander", "welded_wire_mesh"}:
        xlabel = "Deformación unitaria de tracción, εs [mm/mm]"
        ylabel = "Esfuerzo de tracción, fs [MPa]"
    else:
        xlabel = "Deformación unitaria de compresión, εc [mm/mm]"
        ylabel = "Esfuerzo de compresión, fc [MPa]"
    return {
        "title": f"Modelo de {MODEL_LABELS.get(canonical_key, canonical_key.replace('_', ' '))}",
        "subtitle": "Curva esfuerzo-deformación con puntos notables",
        "xlabel": xlabel,
        "ylabel": ylabel,
    }


def split_constitutive_model_reports(calculated_parameters_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Split the calculated-parameter report into one report per constitutive model."""

    reports: dict[str, dict[str, Any]] = {}
    for model_key in CONSTITUTIVE_MODEL_REPORT_KEYS:
        section = calculated_parameters_report[model_key]
        datos_de_salida = deepcopy(section["parameters"])
        if model_key in CONFINED_CONCRETE_MODEL_KEYS:
            datos_de_salida["parametros_de_confinamiento"] = deepcopy(calculated_parameters_report["confinement"])
            datos_de_salida["geometria_resuelta"] = deepcopy(calculated_parameters_report["resolved_geometry"])
        model_report = {
            "stage_id": calculated_parameters_report["stage_id"],
            "title": calculated_parameters_report["title"],
            "source_inputs": calculated_parameters_report["source_inputs"],
            "units": calculated_parameters_report["units"],
            "model": {
                "key": model_key,
                "title": section["title"],
                "description": section["description"],
            },
            "datos_de_entrada": deepcopy(section.get("inputs_used", {})),
            "datos_de_salida": datos_de_salida,
        }
        reports[model_key] = model_report
    return reports

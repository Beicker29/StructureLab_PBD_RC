"""Flujo de Etapa 1: caracterizacion de materiales."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

from structurelab_pbd_rc.core.curves import curve_rows
from structurelab_pbd_rc.core.validation import require_keys, require_positive
from structurelab_pbd_rc.io.read_config import load_yaml_config
from structurelab_pbd_rc.mechanics.geometry.confined_core import derive_confined_core_from_cover
from structurelab_pbd_rc.mechanics.geometry.rebar_layouts import RebarLayout
from structurelab_pbd_rc.mechanics.geometry.reinforced_concrete import ReinforcedConcreteSection
from structurelab_pbd_rc.mechanics.geometry.sections import RectangularSection
from structurelab_pbd_rc.mechanics.geometry.transverse_reinforcement import TransverseReinforcement
from structurelab_pbd_rc.io.paths import stage_results_json_path
from structurelab_pbd_rc.io.write_results import write_csv_rows, write_json_result, write_yaml_result
from structurelab_pbd_rc.mechanics.materials.concrete.attard_setunge import AttardSetungeConcreteModel, AttardSetungeParameters
from structurelab_pbd_rc.mechanics.materials.concrete.confinement import (
    RectangularConfinementGeometry,
    calculate_rectangular_confinement_parameters,
)
from structurelab_pbd_rc.mechanics.materials.concrete.mander_adjusted import ManderAdjustedConcreteModel, ManderAdjustedParameters
from structurelab_pbd_rc.mechanics.materials.concrete.mander_classic import ManderClassicConcreteModel, ManderClassicParameters
from structurelab_pbd_rc.mechanics.materials.concrete.unconfined import UnconfinedConcreteModel, UnconfinedConcreteParameters
from structurelab_pbd_rc.mechanics.materials.library.mesh_database import get_mesh_properties, mesh_diameter_exists
from structurelab_pbd_rc.mechanics.materials.library.rebar_database import get_rebar_properties, rebar_exists
from structurelab_pbd_rc.mechanics.materials.steel.buckling_models import BarBucklingParameters, BucklingSteelCompressionModel
from structurelab_pbd_rc.mechanics.materials.steel.compression_models import SteelCompressionModel, SteelCompressionParameters
from structurelab_pbd_rc.mechanics.materials.steel.tension_models import ManderSteelTensionModel, SteelTensionParameters
from structurelab_pbd_rc.mechanics.materials.steel.welded_wire_mesh import CarrilloWeldedWireMeshModel, WeldedWireMeshParameters
from structurelab_pbd_rc.mechanics.performance.ductility import calculate_curve_metrics_table
from structurelab_pbd_rc.reports.export_excel import write_xlsx
from structurelab_pbd_rc.reports.export_quarto import render_quarto_pdf, write_quarto_source
from structurelab_pbd_rc.reports.model_reports import (
    canonical_model_key,
    model_plot_text,
    report_equation,
    report_section,
    report_value,
    split_constitutive_model_reports,
)
from structurelab_pbd_rc.reports.plots import (
    plot_confined_core_sketch,
    plot_single_model_curve_with_notable_points,
    plot_stress_strain_curves,
)
from structurelab_pbd_rc.design.stages._base import prepare_stage_from_config

DEFAULT_CONFIG_PATH = Path("configs/stages/stage_01_material_characterization.yaml")

REQUIRED_TOP_LEVEL_KEYS = (
    "units",
    "source_reference",
    "section",
    "concrete",
    "longitudinal_reinforcement",
    "transverse_reinforcement",
    "welded_wire_mesh",
    "model_inputs",
)

AVAILABLE_MODELS = {
    "mander_classic_unconfined_concrete",
    "mander_classic_confined_concrete",
    "mander_adjusted_confined_concrete",
    "attard_setunge_unconfined_concrete",
    "attard_setunge_confined_concrete",
    "steel_tension_mander",
    "steel_compression_no_buckling",
    "steel_compression_with_buckling",
    "welded_wire_mesh",
}


def validate_stage_01_config(config: dict[str, Any]) -> None:
    """Validate the minimum editable structure required by Etapa 1."""

    require_keys(config, REQUIRED_TOP_LEVEL_KEYS, context="stage_01 configuration")
    require_keys(config["units"], ["length", "force", "moment", "stress", "strain"], context="units")
    expected_units = {"length": "mm", "force": "kN", "moment": "kN-m", "stress": "MPa", "strain": "mm/mm"}
    for key, expected in expected_units.items():
        actual = config["units"].get(key)
        if actual != expected:
            raise ValueError(f"Unsupported unit for {key}: expected {expected}, got {actual}")
    require_keys(config["section"], ["type", "width", "height", "clear_cover_to_tie"], context="section")
    require_keys(config["section"], ["confined_core"], context="section")
    require_keys(config["section"]["confined_core"], ["clear_spacing_wi"], context="section.confined_core")
    require_keys(config["section"]["confined_core"]["clear_spacing_wi"], ["values"], context="section.confined_core.clear_spacing_wi")
    if not config["section"]["confined_core"]["clear_spacing_wi"]["values"]:
        raise ValueError("section.confined_core.clear_spacing_wi.values must contain at least one wi spacing.")
    require_keys(
        config["concrete"],
        [
            "f_co",
            "Ec_expression",
            "ft_expression",
            "Et_expression",
            "epsilon_t_expression",
            "epsilon_co",
            "epsilon_sp",
        ],
        context="concrete",
    )
    require_keys(
        config["model_inputs"],
        [
            "mander_classic_unconfined_concrete",
            "confinement",
            "mander_classic_confined_concrete",
            "mander_adjusted_confined_concrete",
            "attard_setunge_unconfined_concrete",
            "attard_setunge_confined_concrete",
            "steel_tension_mander",
            "steel_compression_no_buckling",
            "steel_compression_with_buckling",
            "welded_wire_mesh",
        ],
        context="model_inputs",
    )
    require_keys(
        config["longitudinal_reinforcement"],
        ["count", "bar_mark", "diameter", "steel"],
        context="longitudinal_reinforcement",
    )
    require_positive(float(config["longitudinal_reinforcement"]["count"]), name="longitudinal_reinforcement.count")
    if not rebar_exists(str(config["longitudinal_reinforcement"]["bar_mark"])):
        get_rebar_properties(str(config["longitudinal_reinforcement"]["bar_mark"]))
    require_keys(
        config["longitudinal_reinforcement"]["steel"],
        [
            "fy",
            "epsilon_y",
            "Es",
            "f_sh",
            "epsilon_sh",
            "f_su",
            "epsilon_su",
            "P",
            "Et",
        ],
        context="longitudinal_reinforcement.steel",
    )
    require_keys(
        config["transverse_reinforcement"],
        ["type", "bar_mark", "diameter", "spacing", "fyh"],
        context="transverse_reinforcement",
    )
    if not rebar_exists(str(config["transverse_reinforcement"]["bar_mark"])):
        get_rebar_properties(str(config["transverse_reinforcement"]["bar_mark"]))
    require_keys(
        config["welded_wire_mesh"],
        ["include_for_comparison", "default_diameter", "selectable_diameters", "mechanical_properties"],
        context="welded_wire_mesh",
    )
    mesh_diameter = int(config["welded_wire_mesh"]["default_diameter"])
    if not mesh_diameter_exists(mesh_diameter):
        get_mesh_properties(mesh_diameter)
    for model in config["concrete"].get("models", []):
        if model not in AVAILABLE_MODELS:
            raise ValueError(f"Requested model is not available: {model}")
    if config["welded_wire_mesh"].get("model") != "carrillo_2019_welded_wire_mesh":
        raise ValueError("Unsupported welded wire mesh model requested.")
    sign_convention = config.get("curve_generation", {}).get("sign_convention", {})
    for key in ("compression", "tension"):
        value = sign_convention.get(key)
        if value not in {"positive", "negative"}:
            raise ValueError(f"Unsupported sign convention for {key}: expected positive or negative, got {value}")


def _value(config_block: dict[str, Any]) -> float:
    """Return numeric value from a YAML `{value, unit}` block."""

    if not isinstance(config_block, dict):
        return float(config_block)
    return float(config_block["value"])


def _optional_value(config_block: dict[str, Any] | None) -> float | None:
    """Return a numeric value when a YAML block exists and is not null/auto."""

    if not config_block:
        return None
    if not isinstance(config_block, dict):
        return float(config_block)
    value = config_block.get("value")
    if value is None or value == "auto":
        return None
    return float(value)


def _steel_post_yield_modulus(steel: dict[str, Any]) -> float:
    """Return Et from YAML or derive it from Colombian steel mean values."""

    configured = _optional_value(steel.get("Et"))
    if configured is not None:
        return configured

    fy = _value(steel["fy"])
    eps_y = _value(steel["epsilon_y"])
    f_sh = _value(steel["f_sh"])
    eps_sh = _value(steel["epsilon_sh"])
    return (f_sh - fy) / max(eps_sh - eps_y, 1e-9)


def _format_number(value: float, digits: int = 6) -> str:
    """Return compact decimal text for equations written in reports."""

    return f"{value:.{digits}g}"


def _mander_unconfined_constitutive_function(parameters: dict[str, object]) -> dict[str, object]:
    """Return the Mander unconfined concrete function with calculated values inserted."""

    f_co = float(parameters["f_co_mpa"])
    ec = float(parameters["Ec_mpa"])
    epsilon_co = float(parameters["epsilon_peak"])
    epsilon_2co = float(parameters["epsilon_2co"])
    epsilon_sp = float(parameters["epsilon_sp"])
    ft = float(parameters["ft_mpa"])
    et = float(parameters["Et_mpa"])
    epsilon_t = float(parameters["epsilon_t"])
    r = float(parameters["r"])
    stress_at_2co = f_co * 2.0 * r / (r - 1.0 + 2.0**r)

    return {
        "description": "Funcion constitutiva usada para graficar el concreto no confinado de Mander.",
        "variable": "epsilon_c",
        "stress": "fc",
        "branches": [
            {
                "range": f"-{_format_number(epsilon_t)} <= epsilon_c < 0",
                "equation": f"fc = {_format_number(et)} * epsilon_c",
                "units": {"epsilon_c": "[mm/mm]", "fc": "[MPa]"},
            },
            {
                "range": f"0 <= epsilon_c <= {_format_number(epsilon_2co)}",
                "equation": (
                    "fc = "
                    f"{_format_number(f_co)} * (epsilon_c / {_format_number(epsilon_co)}) * {_format_number(r)} "
                    f"/ ({_format_number(r)} - 1 + (epsilon_c / {_format_number(epsilon_co)})^{_format_number(r)})"
                ),
                "units": {"epsilon_c": "[mm/mm]", "fc": "[MPa]"},
            },
            {
                "range": f"{_format_number(epsilon_2co)} < epsilon_c <= {_format_number(epsilon_sp)}",
                "equation": (
                    "fc = "
                    f"{_format_number(stress_at_2co)} * "
                    f"(({_format_number(epsilon_sp)} - epsilon_c) / "
                    f"({_format_number(epsilon_sp)} - {_format_number(epsilon_2co)}))"
                ),
                "units": {"epsilon_c": "[mm/mm]", "fc": "[MPa]"},
            },
            {
                "range": f"epsilon_c > {_format_number(epsilon_sp)}",
                "equation": "fc = 0",
                "units": {"epsilon_c": "[mm/mm]", "fc": "[MPa]"},
            },
        ],
        "reference_values": {
            "f_co": report_value(f_co, "MPa"),
            "Ec": report_value(ec, "MPa"),
            "Esec": report_value(float(parameters["Esec_mpa"]), "MPa"),
            "r": report_value(r, "-"),
            "epsilon_co": report_value(epsilon_co, "mm/mm"),
            "epsilon_2co": report_value(epsilon_2co, "mm/mm"),
            "epsilon_sp": report_value(epsilon_sp, "mm/mm"),
            "ft": report_value(ft, "MPa"),
            "Et": report_value(et, "MPa"),
            "epsilon_t": report_value(epsilon_t, "mm/mm"),
        },
    }


def _report_item_text(name: str, item: dict[str, object]) -> str:
    """Return one readable line for a report parameter item."""

    value = item.get("value")
    unit = item.get("unit", "")
    equation = item.get("equation")
    if equation:
        return f"- {name}: {value} {unit}; ecuacion: {equation}"
    return f"- {name}: {value} {unit}"


def build_mander_unconfined_memory_lines(model_report: dict[str, Any]) -> list[str]:
    """Build a text memory for the Mander unconfined concrete model."""

    model = model_report["model"]
    parameters = model_report.get("datos_de_salida", model.get("parameters", {}))
    inputs_used = model_report.get("datos_de_entrada", model.get("inputs_used", {}))
    constitutive_function = parameters["constitutive_function"]

    lines = [
        "StructureLab_PBD_RC",
        "Memoria de calculo - Modelo de Mander clasico no confinado",
        "",
        f"Etapa: {model_report['stage_id']} - {model_report['title']}",
        f"Fuente de datos: {model_report['source_inputs']}",
        "",
        "1. Alcance",
        "Esta memoria resume los datos de entrada, parametros calculados y la funcion constitutiva usada para el modelo de concreto no confinado de Mander.",
        "Por el momento se limita al modelo mander_classic_unconfined_concrete.",
        "",
        "2. Unidades",
    ]
    for key, value in model_report["units"].items():
        lines.append(f"- {key}: [{value}]")

    lines.extend(["", "3. Datos de entrada"])
    for key, value in inputs_used.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "4. Datos de salida"])
    for key in ("f_co", "Ec", "ft", "Et", "epsilon_t", "epsilon_co", "epsilon_2co", "epsilon_sp", "Esec", "r"):
        lines.append(_report_item_text(key, parameters[key]))

    lines.extend(["", "5. Funcion constitutiva por ramas"])
    lines.append(str(constitutive_function["description"]))
    lines.append(f"Variable independiente: {constitutive_function['variable']}")
    lines.append(f"Variable dependiente: {constitutive_function['stress']}")
    for branch in constitutive_function["branches"]:
        lines.append(f"- Rango: {branch['range']}")
        lines.append(f"  Ecuacion: {branch['equation']}")

    lines.extend(["", "6. Valores de referencia"])
    for key, value in constitutive_function["reference_values"].items():
        lines.append(_report_item_text(key, value))

    lines.extend(
        [
            "",
            "7. Archivos asociados",
            "- YAML del modelo: outputs/stage_01/reports/mander_classic_unconfined_concrete/mander_classic_unconfined_concrete.yaml",
            "- Figura del modelo: outputs/stage_01/figures/models/mander_classic_unconfined_concrete.png",
            "- Datos CSV/XLSX: outputs/stage_01/data/models/mander_classic_unconfined_concrete/",
        ]
    )
    return lines


def _markdown_value(item: dict[str, object]) -> str:
    """Return a compact value with units for Markdown tables."""

    return f"{_format_number(float(item['value']))} {item.get('unit', '')}"


def _spanish_date(today: date | None = None) -> str:
    """Return a date label in Spanish."""

    months = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )
    current = today or date.today()
    return f"{current.day} de {months[current.month - 1]} de {current.year}"


def _mander_unconfined_input_rows(inputs_used: dict[str, object]) -> str:
    """Return Spanish input rows for the Mander unconfined memory."""

    rows = (
        (
            "Resistencia máxima del concreto no confinado",
            "$f'_{co}$",
            f"{_format_number(float(inputs_used['f_co']))} [MPa]",
        ),
        (
            "Expresión del esfuerzo último a tracción",
            "$f_t$",
            "$0.62\\sqrt{f'_{co}}$",
        ),
        ("Módulo elástico usado en tracción", "$E_t$", "$E_t = E_c$"),
        (
            "Expresión de la deformación de tracción",
            "$\\varepsilon_t$",
            "$\\varepsilon_t = f_t/E_t$",
        ),
        (
            "Deformación asociada a la resistencia máxima",
            "$\\varepsilon_{co}$",
            f"{_format_number(float(inputs_used['epsilon_co']))} [mm/mm]",
        ),
        (
            "Deformación de descascaramiento",
            "$\\varepsilon_{sp}$",
            f"{_format_number(float(inputs_used['epsilon_sp']))} [mm/mm]",
        ),
    )
    return "\n".join(f"| {description} | {symbol} | {value} |" for description, symbol, value in rows)


def _mander_unconfined_parameter_rows(parameters: dict[str, dict[str, object]]) -> str:
    """Return Spanish calculated-parameter rows for the Mander unconfined memory."""

    rows = (
        ("Resistencia máxima del concreto no confinado", "$f'_{co}$", "f_co", "-"),
        ("Módulo elástico del concreto", "$E_c$", "Ec", "$4700\\sqrt{f'_{co}}$"),
        ("Esfuerzo último a tracción del concreto", "$f_t$", "ft", "$0.62\\sqrt{f'_{co}}$"),
        ("Módulo elástico en tracción", "$E_t$", "Et", "$E_t = E_c$"),
        ("Deformación de tracción", "$\\varepsilon_t$", "epsilon_t", "$f_t/E_t$"),
        ("Deformación en la resistencia máxima", "$\\varepsilon_{co}$", "epsilon_co", "-"),
        ("Límite de la rama curva de compresión", "$2\\varepsilon_{co}$", "epsilon_2co", "$2\\varepsilon_{co}$"),
        ("Deformación de descascaramiento", "$\\varepsilon_{sp}$", "epsilon_sp", "-"),
        ("Módulo secante", "$E_{sec}$", "Esec", "$f'_{co}/\\varepsilon_{co}$"),
        ("Parámetro de forma de Mander", "$r$", "r", "$E_c/(E_c-E_{sec})$"),
    )
    return "\n".join(
        f"| {description} | {symbol} | {_markdown_value(parameters[key])} | {equation} |"
        for description, symbol, key, equation in rows
    )


def _report_parameter_value(parameters: dict[str, dict[str, object]], key: str) -> float:
    """Return the numeric value of one calculated report parameter."""

    return float(parameters[key]["value"])


def _mander_unconfined_display_from_outputs(parameters: dict[str, dict[str, object]]) -> dict[str, Any]:
    """Build Quarto-only mathematical notation from calculated YAML outputs."""

    f_co = _report_parameter_value(parameters, "f_co")
    et = _report_parameter_value(parameters, "Et")
    epsilon_t = _report_parameter_value(parameters, "epsilon_t")
    epsilon_co = _report_parameter_value(parameters, "epsilon_co")
    epsilon_2co = _report_parameter_value(parameters, "epsilon_2co")
    epsilon_sp = _report_parameter_value(parameters, "epsilon_sp")
    r = _report_parameter_value(parameters, "r")
    stress_at_2co = f_co * 2.0 * r / (r - 1.0 + 2.0**r)

    return {
        "variable": "$\\varepsilon_c$",
        "stress": "$f_c$",
        "definition": "$x = \\dfrac{\\varepsilon_c}{\\varepsilon_{co}}$",
        "ascending_branch": "$f_c = f'_{co}\\dfrac{x r}{r - 1 + x^r}$",
        "ascending_branch_with_values": (
            f"$f_c = {_format_number(f_co)}"
            f"\\dfrac{{(\\varepsilon_c/{_format_number(epsilon_co)})({_format_number(r)})}}"
            f"{{{_format_number(r)} - 1 + (\\varepsilon_c/{_format_number(epsilon_co)})^{{{_format_number(r)}}}}}$"
        ),
        "branches": [
            {
                "range": f"$-{_format_number(epsilon_t)} \\leq \\varepsilon_c < 0$",
                "equation": f"$f_c = {_format_number(et)}\\,\\varepsilon_c$",
            },
            {
                "range": f"$0 \\leq \\varepsilon_c \\leq {_format_number(epsilon_2co)}$",
                "equation": (
                    f"$f_c = {_format_number(f_co)}"
                    f"\\dfrac{{(\\varepsilon_c/{_format_number(epsilon_co)})({_format_number(r)})}}"
                    f"{{{_format_number(r)} - 1 + (\\varepsilon_c/{_format_number(epsilon_co)})^{{{_format_number(r)}}}}}$"
                ),
            },
            {
                "range": f"${_format_number(epsilon_2co)} < \\varepsilon_c \\leq {_format_number(epsilon_sp)}$",
                "equation": (
                    f"$f_c = {_format_number(stress_at_2co)}"
                    f"\\dfrac{{{_format_number(epsilon_sp)} - \\varepsilon_c}}"
                    f"{{{_format_number(epsilon_sp)} - {_format_number(epsilon_2co)}}}$"
                ),
            },
            {
                "range": f"$\\varepsilon_c > {_format_number(epsilon_sp)}$",
                "equation": "$f_c = 0$",
            },
        ],
        "compact_equation_latex": (
            "f_c(\\varepsilon_c) =\n"
            "\\begin{cases}\n"
            f"{_format_number(et)}\\,\\varepsilon_c,"
            f"& -{_format_number(epsilon_t)} \\leq \\varepsilon_c < 0 \\\\\n"
            f"{_format_number(f_co)}"
            f"\\dfrac{{(\\varepsilon_c/{_format_number(epsilon_co)})({_format_number(r)})}}"
            f"{{{_format_number(r)} - 1 + (\\varepsilon_c/{_format_number(epsilon_co)})^{{{_format_number(r)}}}}},"
            f"& 0 \\leq \\varepsilon_c \\leq {_format_number(epsilon_2co)} \\\\\n"
            f"{_format_number(stress_at_2co)}"
            f"\\dfrac{{{_format_number(epsilon_sp)} - \\varepsilon_c}}"
            f"{{{_format_number(epsilon_sp)} - {_format_number(epsilon_2co)}}},"
            f"& {_format_number(epsilon_2co)} < \\varepsilon_c \\leq {_format_number(epsilon_sp)} \\\\\n"
            f"0, & \\varepsilon_c > {_format_number(epsilon_sp)}\n"
            "\\end{cases}"
        ),
    }


def _math_block(inline_math: str) -> str:
    """Convert YAML inline math into display math for Quarto."""

    expression = inline_math.strip()
    if expression.startswith("$") and expression.endswith("$"):
        expression = expression[1:-1]
    return f"$$\n{expression}\n$$"


def _mander_unconfined_branch_blocks(display: dict[str, Any]) -> str:
    """Return readable branch blocks from Quarto-only display metadata."""

    titles = (
        "Rama de tracción",
        "Rama ascendente de compresión",
        "Rama descendente hasta descascaramiento",
        "Rama posterior al descascaramiento",
    )
    blocks: list[str] = []
    for title, branch in zip(titles, display["branches"]):
        blocks.extend(
            [
                f"**{title}.**",
                "",
                f"Rango: {branch['range']}",
                "",
                _math_block(branch["equation"]),
            ]
        )
    return "\n\n".join(blocks)


def build_mander_unconfined_quarto_document(model_report: dict[str, Any]) -> str:
    """Build a Quarto document using only the already-generated model YAML data."""

    model = model_report["model"]
    parameters = model_report.get("datos_de_salida", model.get("parameters", {}))
    inputs_used = model_report.get("datos_de_entrada", model.get("inputs_used", {}))
    constitutive_function = parameters["constitutive_function"]
    display = _mander_unconfined_display_from_outputs(parameters)
    figure_path = "assets/mander_classic_unconfined_concrete.png"

    inputs_rows = _mander_unconfined_input_rows(inputs_used)
    parameter_rows = _mander_unconfined_parameter_rows(parameters)
    branch_blocks = _mander_unconfined_branch_blocks(display)
    stage_title = "Caracterización mecánica monotónica de materiales"

    return f"""---
title: "Memoria de cálculo"
subtitle: "Modelo de Mander clásico no confinado"
author: "StructureLab PBD RC"
date: "{_spanish_date()}"
lang: es
format:
  typst:
    papersize: a4
    orientation: portrait
    toc: true
    number-sections: true
---

# Identificación

Esta memoria resume el modelo constitutivo de Mander clásico para concreto no confinado usado en la Etapa 1.
Los valores mostrados se consumen desde el archivo YAML del modelo ya calculado; esta memoria no recalcula parámetros.

- **Etapa:** Etapa 1.
- **Nombre de la etapa:** {stage_title}.
- **Modelo constitutivo:** Mander clásico no confinado.
- **Fuente de datos:** archivo YAML de resultados del modelo.

# Datos de entrada

| Descripción | Símbolo | Valor |
|---|---:|---:|
{inputs_rows}

# Datos de salida

| Descripción | Símbolo | Valor | Ecuación |
|---|---:|---:|---|
{parameter_rows}

Los parámetros principales quedan:

$$
E_c = 4700 \\sqrt{{f'_{{co}}}} = {_format_number(float(parameters["Ec"]["value"]))}\\ \\text{{MPa}}
$$

$$
f_t = 0.62 \\sqrt{{f'_{{co}}}} = {_format_number(float(parameters["ft"]["value"]))}\\ \\text{{MPa}}
$$

$$
E_{{sec}} = \\frac{{f'_{{co}}}}{{\\varepsilon_{{co}}}}
= \\frac{{{_format_number(float(parameters["f_co"]["value"]))}}}{{{_format_number(float(parameters["epsilon_co"]["value"]))}}}
= {_format_number(float(parameters["Esec"]["value"]))}\\ \\text{{MPa}}
$$

$$
r = \\frac{{E_c}}{{E_c - E_{{sec}}}}
= \\frac{{{_format_number(float(parameters["Ec"]["value"]))}}}{{{_format_number(float(parameters["Ec"]["value"]))} - {_format_number(float(parameters["Esec"]["value"]))}}}
= {_format_number(float(parameters["r"]["value"]))}
$$

# Función constitutiva

Se usa compresión positiva y, para la rama de tracción del concreto, deformación y esfuerzo negativos.
La variable independiente es {display["variable"]} y el esfuerzo resultante es {display["stress"]}.

Definiendo:

{display["definition"]}

la rama ascendente de Mander se expresa como:

{display["ascending_branch"]}

Con los valores del modelo:

{display["ascending_branch_with_values"]}

La función usada para graficar queda definida por las siguientes ramas:

{branch_blocks}

En forma compacta:

$$
{display["compact_equation_latex"]}
$$

donde:

$$
\\varepsilon_t = \\frac{{f_t}}{{E_t}}
= \\frac{{{_format_number(float(parameters["ft"]["value"]))}}}{{{_format_number(float(parameters["Et"]["value"]))}}}
= {_format_number(float(parameters["epsilon_t"]["value"]))}
$$

$$
2\\varepsilon_{{co}} = {_format_number(float(parameters["epsilon_2co"]["value"]))}
\\qquad
\\varepsilon_{{sp}} = {_format_number(float(parameters["epsilon_sp"]["value"]))}
$$

# Curva generada

![Curva esfuerzo-deformación del modelo de Mander clásico no confinado.]({figure_path}){{width=100%}}

# Archivos asociados

- Archivo de entrada: `configs/stages/stage_01_material_characterization.yaml`
- Archivo de resultados del modelo: `outputs/stage_01/reports/mander_classic_unconfined_concrete/mander_classic_unconfined_concrete.yaml`
- Datos de la curva en formatos CSV y XLSX: `outputs/stage_01/data/models/mander_classic_unconfined_concrete/`
- Figura de la curva: `outputs/stage_01/figures/models/mander_classic_unconfined_concrete.png`
"""


def _mm_to_cm(value_mm: float) -> float:
    """Convert millimeters from YAML to centimeters for legacy geometry APIs."""

    return value_mm / 10.0


def _wi_cm_from_config(config: dict[str, Any]) -> tuple[float, ...]:
    """Return the explicit wi list from YAML, converted from millimeters to centimeters."""

    wi_values = config["section"]["confined_core"]["clear_spacing_wi"]["values"]
    return tuple(_mm_to_cm(_value(wi)) for wi in wi_values)


def _geometry_summary_for_report(geometry_summary: dict[str, object]) -> dict[str, object]:
    """Return geometry with SI project units for user-facing reports."""

    gross = geometry_summary["gross_section"]
    core = geometry_summary["confined_core"]
    longitudinal = geometry_summary["longitudinal_reinforcement"]
    transverse = geometry_summary["transverse_reinforcement"]
    return {
        "gross_section": {
            "width": float(gross["width_cm"]) * 10.0,
            "height": float(gross["height_cm"]) * 10.0,
            "area": float(gross["area_cm2"]) * 100.0,
        },
        "confined_core": {
            "boundary": core["boundary"],
            "width": float(core["width_cm"]) * 10.0,
            "height": float(core["height_cm"]) * 10.0,
            "area": float(core["area_cm2"]) * 100.0,
        },
        "longitudinal_reinforcement": {
            "bar_count": longitudinal["bar_count"],
            "bar_mark": longitudinal["bar_mark"],
            "bar_diameter": longitudinal["bar_diameter_mm"],
            "single_bar_area": longitudinal["single_bar_area_mm2"],
            "total_area": longitudinal["total_area_mm2"],
            "layout_description": longitudinal["layout_description"],
            "longitudinal_ratio": longitudinal.get("longitudinal_ratio"),
        },
        "transverse_reinforcement": {
            "type": transverse["reinforcement_type"],
            "bar_mark": transverse["bar_mark"],
            "diameter": transverse["diameter_mm"],
            "bar_area": transverse["bar_area_mm2"],
            "spacing": transverse["spacing_mm"],
            "legs_x": transverse["legs_x"],
            "legs_y": transverse["legs_y"],
            "area_x": transverse["area_x_mm2"],
            "area_y": transverse["area_y_mm2"],
        },
        "clear_cover_to_tie": float(geometry_summary["clear_cover_to_tie_cm"]) * 10.0,
        "longitudinal_ratio": geometry_summary["longitudinal_ratio"],
    }


def _resolve_source_pdf(config: dict[str, Any]) -> str | None:
    """Resolve the source PDF path, allowing glob fallback for encoded names."""

    source = config.get("source_reference", {})
    pdf_path = Path(str(source.get("pdf", "")))
    if pdf_path.exists():
        return str(pdf_path)
    pattern = source.get("pdf_search_pattern")
    if pattern:
        matches = sorted(Path().glob(str(pattern)))
        if matches:
            return str(matches[0])
    return None


def build_geometry_and_confinement(config: dict[str, Any]) -> tuple[dict[str, object], dict[str, object]]:
    """Build geometry and confinement summaries from YAML."""

    section_config = config["section"]
    assumptions = section_config
    gross_section = RectangularSection(
        width_cm=_mm_to_cm(_value(section_config["width"])),
        height_cm=_mm_to_cm(_value(section_config["height"])),
    )
    longitudinal = RebarLayout(
        bar_count=int(config["longitudinal_reinforcement"]["count"]),
        bar_mark=str(config["longitudinal_reinforcement"]["bar_mark"]),
        layout_description="symmetric perimeter layout",
    )
    transverse = TransverseReinforcement(
        reinforcement_type=str(config["transverse_reinforcement"]["type"]),
        bar_mark=str(config["transverse_reinforcement"]["bar_mark"]),
        spacing_cm=_mm_to_cm(_value(config["transverse_reinforcement"]["spacing"])),
        diameter_mm=_value(config["transverse_reinforcement"]["diameter"]),
        legs_x=int(assumptions.get("transverse_legs_x", 2)),
        legs_y=int(assumptions.get("transverse_legs_y", 2)),
    )
    rc_section = ReinforcedConcreteSection(
        gross_section=gross_section,
        longitudinal_reinforcement=longitudinal,
        transverse_reinforcement=transverse,
        clear_cover_to_tie_cm=_mm_to_cm(_value(section_config["clear_cover_to_tie"])),
    )
    confined_core = derive_confined_core_from_cover(
        gross_width_cm=gross_section.width_cm,
        gross_height_cm=gross_section.height_cm,
        clear_cover_to_tie_cm=rc_section.clear_cover_to_tie_cm,
        tie_bar_diameter_mm=transverse.effective_diameter_mm,
        boundary=str(assumptions.get("confined_core_boundary", "tie_centerline")),
    )
    confinement_geometry = RectangularConfinementGeometry.from_core(
        confined_core,
        transverse,
        longitudinal_steel_area_cm2=longitudinal.total_area_cm2,
        longitudinal_bars_per_side=int(assumptions.get("longitudinal_bars_per_side", 5)),
        clear_spacing_wi_cm=_wi_cm_from_config(config),
    )
    confinement = calculate_rectangular_confinement_parameters(
        confinement_geometry,
        transverse_area_x_mm2=transverse.area_x_mm2,
        transverse_area_y_mm2=transverse.area_y_mm2,
        transverse_yield_strength_mpa=_value(config["transverse_reinforcement"]["fyh"]),
    )
    geometry_summary = rc_section.as_dict()
    geometry_summary["confined_core"] = confined_core.as_dict()
    geometry_summary["longitudinal_bars_per_side"] = int(assumptions.get("longitudinal_bars_per_side", 5))
    geometry_summary["geometry_assumptions"] = {
        key: value
        for key, value in assumptions.items()
        if key
        in {
            "confined_core_boundary",
            "longitudinal_bars_per_side",
            "transverse_legs_x",
            "transverse_legs_y",
        }
    }
    return geometry_summary, confinement.as_dict()


def generate_material_curves(
    config: dict[str, Any],
    confinement_parameters: dict[str, object],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    """Generate concrete, steel and mesh curves."""

    curve_config = config.get("curve_generation", {})
    num_points = int(curve_config.get("num_points", 401))
    sign_convention = curve_config.get("sign_convention", {})
    tension_sign = str(sign_convention.get("tension", "positive"))
    concrete = config["concrete"]
    steel = config["longitudinal_reinforcement"]["steel"]
    transverse = config["transverse_reinforcement"]

    fc = _value(concrete["f_co"])
    ec = 4700.0 * fc**0.5
    eps_co = _value(concrete["epsilon_co"])
    eps_sp = _value(concrete["epsilon_sp"])
    ft = 0.62 * fc**0.5
    eps_su_tie = _value(transverse.get("epsilon_su", 0.10))

    from structurelab_pbd_rc.mechanics.materials.concrete.confinement import ConfinementParameters

    confinement = ConfinementParameters(
        rho_x=float(confinement_parameters["rho_x"]),
        rho_y=float(confinement_parameters["rho_y"]),
        rho_s=float(confinement_parameters["rho_s"]),
        rho_cc=float(confinement_parameters["rho_cc"]),
        ke=float(confinement_parameters["ke"]),
        fl_eff_mpa=float(confinement_parameters["fl_eff_mpa"]),
        transverse_yield_strength_mpa=float(confinement_parameters["transverse_yield_strength_mpa"]),
        clear_tie_spacing_cm=float(confinement_parameters["clear_tie_spacing_cm"]),
        wi_x_cm=float(confinement_parameters["wi_x_cm"]),
        wi_y_cm=float(confinement_parameters["wi_y_cm"]),
        wi_cm=[float(wi) for wi in confinement_parameters["wi_cm"]],
        sum_wi2_cm2=float(confinement_parameters["sum_wi2_cm2"]),
        assumptions=list(confinement_parameters["assumptions"]),
    )

    unconfined_model = UnconfinedConcreteModel(
        UnconfinedConcreteParameters(
            f_c_mpa=fc,
            epsilon_co=eps_co,
            epsilon_sp=eps_sp,
            elastic_modulus_mpa=ec,
            tensile_strength_mpa=ft,
            tensile_modulus_mpa=ec,
        )
    )
    mander_classic_model = ManderClassicConcreteModel(
        ManderClassicParameters(
            f_c_mpa=fc,
            elastic_modulus_mpa=ec,
            epsilon_co=eps_co,
            transverse_steel_ultimate_strain=eps_su_tie,
            confinement=confinement,
        )
    )
    mander_adjusted_model = ManderAdjustedConcreteModel(
        ManderAdjustedParameters(
            f_c_mpa=fc,
            elastic_modulus_mpa=ec,
            epsilon_co=eps_co,
            transverse_steel_ultimate_strain=eps_su_tie,
            confinement=confinement,
        )
    )
    mander_classic_curve = mander_classic_model.generate_curve(num_points)
    mander_adjusted_curve = mander_adjusted_model.generate_curve(num_points)
    concrete_curves = {
        "mander_classic_unconfined_concrete": unconfined_model.generate_curve(
            num_points,
            include_tension_branch=tension_sign == "negative",
            tension_sign=tension_sign,
        ),
        "mander_classic_confined_concrete": mander_classic_curve,
        "mander_adjusted_confined_concrete": mander_adjusted_curve,
        "attard_setunge_unconfined_concrete": AttardSetungeConcreteModel(
            AttardSetungeParameters(f_c_mpa=fc, elastic_modulus_mpa=ec, epsilon_peak=eps_co, epsilon_u=eps_sp)
        ).generate_curve(num_points),
        "attard_setunge_confined_concrete": AttardSetungeConcreteModel(
            AttardSetungeParameters(
                f_c_mpa=fc,
                elastic_modulus_mpa=ec,
                epsilon_peak=eps_co,
                epsilon_u=eps_sp,
                confined=True,
                confinement_pressure_mpa=confinement.fl_eff_mpa,
            )
        ).generate_curve(num_points),
    }

    fy = _value(steel["fy"])
    es = _value(steel["Es"])
    eps_y = _value(steel["epsilon_y"])
    eps_su = _value(steel["epsilon_su"])
    fu = _value(steel.get("f_su", 1.25 * fy))
    eps_sh = _value(steel["epsilon_sh"])
    et = _steel_post_yield_modulus(steel)
    p_value = _value(steel.get("P", 4.0))
    compression_ultimate_strain = _value(steel["compression_buckling"].get("epsilon_su_compression", 0.08))

    tension_model = ManderSteelTensionModel(
        SteelTensionParameters(
            fy_mpa=fy,
            fu_mpa=fu,
            elastic_modulus_mpa=es,
            epsilon_y=eps_y,
            strain_hardening_modulus_mpa=et,
            epsilon_sh=eps_sh,
            epsilon_su=eps_su,
            parameter_p=float(p_value),
        )
    )
    compression_model = SteelCompressionModel(
        SteelCompressionParameters(
            fy_mpa=fy,
            fu_mpa=fu,
            elastic_modulus_mpa=es,
            epsilon_y=eps_y,
            epsilon_su_compression=compression_ultimate_strain,
            epsilon_sh=eps_sh,
            strain_hardening_modulus_mpa=et,
            parameter_p=float(p_value),
        )
    )
    buckling_model = BucklingSteelCompressionModel(
        BarBucklingParameters(
            transverse_spacing_cm=_mm_to_cm(_value(transverse["spacing"])),
            longitudinal_bar_diameter_mm=_value(config["longitudinal_reinforcement"]["diameter"]),
            fy_mpa=fy,
            elastic_modulus_mpa=es,
            epsilon_y=eps_y,
            degradation_alpha=_value(steel["compression_buckling"].get("degradation_alpha", 3.0)),
            ultimate_strain=compression_ultimate_strain,
        )
    )
    steel_curves = {
        "steel_tension_mander": tension_model.generate_curve(num_points),
        "steel_compression_no_buckling": compression_model.generate_curve(num_points),
        "steel_compression_with_buckling": buckling_model.generate_curve(num_points),
    }

    mesh_diameter = int(config["welded_wire_mesh"]["default_diameter"])
    mesh_data = get_mesh_properties(mesh_diameter)
    mesh_model = CarrilloWeldedWireMeshModel(
        WeldedWireMeshParameters(
            diameter_mm=mesh_diameter,
            fy_mpa=float(mesh_data["fy_mpa"]),
            fu_mpa=float(mesh_data["fu_mpa"]),
            epsilon_u=float(mesh_data["epsilon_u"]),
            elastic_modulus_mpa=es,
        )
    )
    mesh_curves = {"welded_wire_mesh": mesh_model.generate_curve(num_points)}
    return concrete_curves, steel_curves, mesh_curves


def build_calculated_parameters_report(
    config: dict[str, Any],
    *,
    geometry_summary: dict[str, object],
    confinement_parameters: dict[str, object],
    curves: dict[str, dict[str, object]],
) -> dict[str, Any]:
    """Build a YAML-ready report of calculated parameters by material model."""

    concrete = config["concrete"]
    steel = config["longitudinal_reinforcement"]["steel"]
    transverse = config["transverse_reinforcement"]
    fc = _value(concrete["f_co"])
    ec = 4700.0 * fc**0.5
    ft = 0.62 * fc**0.5
    concrete_tension_modulus = ec
    eps_t = ft / max(concrete_tension_modulus, 1e-9)
    fy = _value(steel["fy"])
    f_sh = _value(steel["f_sh"])
    eps_y = _value(steel["epsilon_y"])
    eps_sh = _value(steel["epsilon_sh"])
    et = _steel_post_yield_modulus(steel)

    concrete_models = {name: curves[name]["parameters"] for name in curves if name in {
        "mander_classic_unconfined_concrete",
        "mander_classic_confined_concrete",
        "mander_adjusted_confined_concrete",
        "attard_setunge_unconfined_concrete",
        "attard_setunge_confined_concrete",
    }}
    steel_models = {name: curves[name]["parameters"] for name in curves if name.startswith("steel_")}
    mesh_model = curves["welded_wire_mesh"]["parameters"]
    selected_mesh_diameter = int(config["welded_wire_mesh"]["default_diameter"])
    selected_mesh_properties = config["welded_wire_mesh"]["mechanical_properties"][selected_mesh_diameter]

    return {
        "stage_id": config["stage_id"],
        "title": config["title"],
        "source_inputs": "configs/stages/stage_01_material_characterization.yaml",
        "units": config["units"],
        "input_data": {
                "title": "Datos de entrada",
                "description": "Datos leidos desde el YAML de la Etapa 1 antes de calcular parametros derivados.",
                "data": {
                    "section": {
                        "type": config["section"]["type"],
                        "width": config["section"]["width"],
                        "height": config["section"]["height"],
                        "clear_cover_to_tie": config["section"]["clear_cover_to_tie"],
                        "confined_core_boundary": config["section"]["confined_core_boundary"],
                        "longitudinal_bars_per_side": config["section"]["longitudinal_bars_per_side"],
                        "transverse_legs_x": config["section"]["transverse_legs_x"],
                        "transverse_legs_y": config["section"]["transverse_legs_y"],
                        "clear_spacing_wi": config["section"]["confined_core"]["clear_spacing_wi"]["values"],
                    },
                    "concrete": {
                        "f_co": config["concrete"]["f_co"],
                        "Ec_expression": config["concrete"]["Ec_expression"],
                        "ft_expression": config["concrete"]["ft_expression"],
                        "Et_expression": config["concrete"]["Et_expression"],
                        "epsilon_t_expression": config["concrete"]["epsilon_t_expression"],
                        "epsilon_co": config["concrete"]["epsilon_co"],
                        "epsilon_sp": config["concrete"]["epsilon_sp"],
                    },
                    "longitudinal_reinforcement": {
                        "count": config["longitudinal_reinforcement"]["count"],
                        "bar_mark": config["longitudinal_reinforcement"]["bar_mark"],
                        "diameter": config["longitudinal_reinforcement"]["diameter"],
                        "steel": config["longitudinal_reinforcement"]["steel"],
                    },
                    "transverse_reinforcement": {
                        "type": config["transverse_reinforcement"]["type"],
                        "bar_mark": config["transverse_reinforcement"]["bar_mark"],
                        "diameter": config["transverse_reinforcement"]["diameter"],
                        "spacing": config["transverse_reinforcement"]["spacing"],
                        "fyh": config["transverse_reinforcement"]["fyh"],
                        "epsilon_su": config["transverse_reinforcement"]["epsilon_su"],
                    },
                    "welded_wire_mesh": {
                        "selected_diameter": selected_mesh_diameter,
                        "selectable_diameters": config["welded_wire_mesh"]["selectable_diameters"],
                        "selected_mechanical_properties": {
                            "fy": selected_mesh_properties["fy"],
                            "fu": selected_mesh_properties["fu"],
                            "epsilon_u": selected_mesh_properties["epsilon_u"],
                        },
                        "model": config["welded_wire_mesh"]["model"],
                    },
                    "curve_generation": config["curve_generation"],
                },
        },
        "resolved_geometry": {
                "title": "Geometria resuelta",
                "description": "Geometria derivada a partir de la seccion, recubrimiento, fleje y arreglo de barras.",
                "data": _geometry_summary_for_report(geometry_summary),
        },
        "confinement": report_section(
                "Parametros de confinamiento",
                "Parametros geometricos y mecanicos comunes para los modelos de concreto confinado.",
                {
                    "rho_x": report_equation(
                        "Ash_x / (core_height * tie_spacing)",
                        confinement_parameters["rho_x"],
                        "-",
                    ),
                    "rho_y": report_equation(
                        "Ash_y / (core_width * tie_spacing)",
                        confinement_parameters["rho_y"],
                        "-",
                    ),
                    "rho_s": report_equation(
                        "rho_x + rho_y",
                        confinement_parameters["rho_s"],
                        "-",
                    ),
                    "rho_cc": report_equation(
                        "A_longitudinal / A_core",
                        confinement_parameters["rho_cc"],
                        "-",
                    ),
                    "sum_wi2": report_equation(
                        "sum(w_i^2)",
                        float(confinement_parameters["sum_wi2_cm2"]) * 100.0,
                        "mm^2",
                        {"w_i": [float(wi) * 10.0 for wi in confinement_parameters["wi_cm"]]},
                    ),
                    "clear_tie_spacing": report_equation(
                        "s - d_tie",
                        float(confinement_parameters["clear_tie_spacing_cm"]) * 10.0,
                        "mm",
                    ),
                    "ke": report_equation(
                        "(1 - sum(w_i^2)/(6*b_c*h_c))*(1 - s_clear/(2*b_c))*(1 - s_clear/(2*h_c))/(1 - rho_cc)",
                        confinement_parameters["ke"],
                        "-",
                    ),
                    "fl_eff": report_equation(
                        "0.5 * ke * rho_s * fyh",
                        confinement_parameters["fl_eff_mpa"],
                        "MPa",
                    ),
                },
                inputs_used={
                    "core_width": float(geometry_summary["confined_core"]["width_cm"]) * 10.0,
                    "core_height": float(geometry_summary["confined_core"]["height_cm"]) * 10.0,
                    "tie_spacing": config["transverse_reinforcement"]["spacing"],
                    "tie_diameter": config["transverse_reinforcement"]["diameter"],
                    "fyh": config["transverse_reinforcement"]["fyh"],
                    "w_i": [float(wi) * 10.0 for wi in confinement_parameters["wi_cm"]],
                },
            ),
        "mander_classic_unconfined_concrete": report_section(
                "Modelo de Mander no confinado",
                "Parametros de compresion y traccion del concreto no confinado.",
                {
                    "f_co": report_value(fc, "MPa"),
                    "Ec": report_equation("4700 * sqrt(f_co)", ec, "MPa", {"f_co": fc}),
                    "ft": report_equation("0.62 * sqrt(f_co)", ft, "MPa", {"f_co": fc}),
                    "Et": report_equation("Et = Ec", concrete_tension_modulus, "MPa", {"Ec": ec}),
                    "epsilon_t": report_equation("ft / Et", eps_t, "mm/mm", {"ft": ft, "Et": concrete_tension_modulus}),
                    "epsilon_co": report_value(concrete_models["mander_classic_unconfined_concrete"]["epsilon_peak"], "m/m"),
                    "epsilon_2co": report_equation(
                        "2 * epsilon_co",
                        concrete_models["mander_classic_unconfined_concrete"]["epsilon_2co"],
                        "mm/mm",
                    ),
                    "epsilon_sp": report_value(concrete_models["mander_classic_unconfined_concrete"]["epsilon_sp"], "mm/mm"),
                    "Esec": report_equation(
                        "f_co / epsilon_co",
                        concrete_models["mander_classic_unconfined_concrete"]["Esec_mpa"],
                        "MPa",
                        {
                            "f_co": fc,
                            "epsilon_co": concrete_models["mander_classic_unconfined_concrete"]["epsilon_peak"],
                        },
                    ),
                    "r": report_equation(
                        "Ec / (Ec - Esec)",
                        concrete_models["mander_classic_unconfined_concrete"]["r"],
                        "-",
                        {
                            "Ec": ec,
                            "Esec": concrete_models["mander_classic_unconfined_concrete"]["Esec_mpa"],
                        },
                    ),
                    "constitutive_function": _mander_unconfined_constitutive_function(
                        concrete_models["mander_classic_unconfined_concrete"]
                    ),
                },
                inputs_used={
                    "f_co": config["concrete"]["f_co"],
                    "ft_expression": config["concrete"]["ft_expression"],
                    "Et_expression": config["concrete"]["Et_expression"],
                    "epsilon_t_expression": config["concrete"]["epsilon_t_expression"],
                    "epsilon_co": config["concrete"]["epsilon_co"],
                    "epsilon_sp": config["concrete"]["epsilon_sp"],
                },
            ),
        "mander_classic_confined_concrete": report_section(
                "Modelo de Mander clasico",
                "Parametros calculados para la curva de concreto confinado con el modelo clasico de Mander.",
                {
                    "ke": report_value(concrete_models["mander_classic_confined_concrete"]["ke"], "-"),
                    "fl_eff": report_value(confinement_parameters["fl_eff_mpa"], "MPa"),
                    "fcc": report_equation(
                        "f_co * (-1.254 + 2.254*sqrt(1 + 7.94*fl/f_co) - 2*fl/f_co)",
                        concrete_models["mander_classic_confined_concrete"]["fcc_mpa"],
                        "MPa",
                    ),
                    "epsilon_cc": report_equation(
                        "epsilon_co * (1 + 5*(fcc/f_co - 1))",
                        concrete_models["mander_classic_confined_concrete"]["eps_cc"],
                        "m/m",
                    ),
                    "epsilon_cu": report_equation(
                        "0.004 + 1.4*rho_s*fyh*epsilon_su_transverse/fcc",
                        concrete_models["mander_classic_confined_concrete"]["eps_cu"],
                        "m/m",
                    ),
                    "Esec": report_equation("fcc / epsilon_cc", concrete_models["mander_classic_confined_concrete"]["Esec_mpa"], "MPa"),
                    "r": report_equation("Ec / (Ec - Esec)", concrete_models["mander_classic_confined_concrete"]["r"], "-"),
                },
                inputs_used={
                    "f_co": fc,
                    "Ec": ec,
                    "epsilon_co": concrete_models["mander_classic_unconfined_concrete"]["epsilon_peak"],
                    "rho_s": confinement_parameters["rho_s"],
                    "fyh": config["transverse_reinforcement"]["fyh"],
                    "epsilon_su_transverse": config["transverse_reinforcement"].get("epsilon_su"),
                },
            ),
        "mander_adjusted_confined_concrete": report_section(
                "Modelo de Mander ajustado",
                "Parametros calculados para la variante ajustada del modelo de Mander.",
                {
                    "ke": report_value(concrete_models["mander_adjusted_confined_concrete"]["ke"], "-"),
                    "fl_eff": report_value(confinement_parameters["fl_eff_mpa"], "MPa"),
                    "fcc": report_equation(
                        "f_co * (1 + 3.5*(fl/f_co)^0.75)",
                        concrete_models["mander_adjusted_confined_concrete"]["fcc_mpa"],
                        "MPa",
                    ),
                    "epsilon_cc": report_equation(
                        "epsilon_co * (1 + 5*(fcc/f_co - 1))",
                        concrete_models["mander_adjusted_confined_concrete"]["eps_cc"],
                        "m/m",
                    ),
                    "epsilon_tst": report_equation(
                        "min(0.6*epsilon_su_transverse, 0.06)",
                        concrete_models["mander_adjusted_confined_concrete"]["eps_tst"],
                        "m/m",
                    ),
                    "epsilon_cu": report_equation(
                        "0.004 + rho_s*fyh*epsilon_tst/fcc",
                        concrete_models["mander_adjusted_confined_concrete"]["eps_cu"],
                        "m/m",
                    ),
                },
                inputs_used={
                    "f_co": fc,
                    "epsilon_co": concrete_models["mander_classic_unconfined_concrete"]["epsilon_peak"],
                    "rho_s": confinement_parameters["rho_s"],
                    "fyh": config["transverse_reinforcement"]["fyh"],
                    "epsilon_su_transverse": config["transverse_reinforcement"].get("epsilon_su"),
                },
            ),
        "attard_setunge_unconfined_concrete": report_section(
                "Modelo Attard-Setunge no confinado",
                "Parametros calculados para la rama no confinada del modelo Attard-Setunge.",
                {
                    "alpha": report_equation(
                        "limit(1.17 - 0.002125*(f_co - 20), 1.00, 1.17)",
                        concrete_models["attard_setunge_unconfined_concrete"]["alpha"],
                        "-",
                    ),
                    "Eti": report_equation("alpha * Ec", concrete_models["attard_setunge_unconfined_concrete"]["Eti_mpa"], "MPa"),
                    "fpl": report_equation("0.45 * f_co", concrete_models["attard_setunge_unconfined_concrete"]["fpl_mpa"], "MPa"),
                    "epsilon_ic": report_equation(
                        "epsilon_co*(2.5 - 0.3*ln(f_co))",
                        concrete_models["attard_setunge_unconfined_concrete"]["epsilon_ic"],
                        "m/m",
                    ),
                    "f_ic": report_equation(
                        "f_co*(1.41 - 0.17*ln(f_co))",
                        concrete_models["attard_setunge_unconfined_concrete"]["f_ic_mpa"],
                        "MPa",
                    ),
                },
                inputs_used={"f_co": fc, "Ec": ec, "epsilon_co": concrete_models["mander_classic_unconfined_concrete"]["epsilon_peak"]},
            ),
        "attard_setunge_confined_concrete": report_section(
                "Modelo Attard-Setunge confinado",
                "Parametros calculados para la rama confinada del modelo Attard-Setunge.",
                {
                    "fcc": report_equation(
                        "f_co * (1 + 10*(fl/f_co)^0.6)",
                        concrete_models["attard_setunge_confined_concrete"]["f_peak_mpa"],
                        "MPa",
                    ),
                    "epsilon_cc": report_equation(
                        "epsilon_co * (1 + (69.4 - 13.2*ln(f_co))*fl/f_co)",
                        concrete_models["attard_setunge_confined_concrete"]["epsilon_peak"],
                        "m/m",
                    ),
                    "fi": report_value(concrete_models["attard_setunge_confined_concrete"]["fi_mpa"], "MPa"),
                    "epsilon_i": report_value(concrete_models["attard_setunge_confined_concrete"]["epsilon_i"], "m/m"),
                    "f_2i": report_value(concrete_models["attard_setunge_confined_concrete"]["f_2i_mpa"], "MPa"),
                    "epsilon_2i": report_value(concrete_models["attard_setunge_confined_concrete"]["epsilon_2i"], "m/m"),
                },
                inputs_used={
                    "f_co": fc,
                    "Ec": ec,
                    "epsilon_co": concrete_models["mander_classic_unconfined_concrete"]["epsilon_peak"],
                    "fl_eff": confinement_parameters["fl_eff_mpa"],
                },
            ),
        "steel_tension_mander": report_section(
                "Acero longitudinal en traccion",
                "Parametros del modelo de Mander para acero longitudinal sometido a traccion monotona.",
                {
                    "fy": report_value(fy, "MPa"),
                    "epsilon_y": report_value(eps_y, "m/m"),
                    "Et": report_equation(
                        "(f_sh - f_y) / (epsilon_sh - epsilon_y)",
                        et,
                        "MPa",
                        {"f_sh": f_sh, "f_y": fy, "epsilon_sh": eps_sh, "epsilon_y": eps_y},
                    ),
                    "f_su": report_value(steel_models["steel_tension_mander"]["fu_mpa"], "MPa"),
                    "epsilon_su": report_value(steel_models["steel_tension_mander"]["eps_su"], "m/m"),
                    "P": report_value(steel_models["steel_tension_mander"]["P"], "-"),
                },
                inputs_used=config["longitudinal_reinforcement"]["steel"],
            ),
        "steel_compression_no_buckling": report_section(
                "Acero longitudinal en compresion sin pandeo",
                "Parametros de la curva de compresion del acero sin degradacion por pandeo.",
                {
                    "fy": report_value(steel_models["steel_compression_no_buckling"]["fy_mpa"], "MPa"),
                    "f_su": report_value(steel_models["steel_compression_no_buckling"]["fu_mpa"], "MPa"),
                    "epsilon_su": report_value(steel_models["steel_compression_no_buckling"]["eps_su"], "m/m"),
                    "Et": report_value(steel_models["steel_compression_no_buckling"]["Et_mpa"], "MPa"),
                },
                inputs_used=config["longitudinal_reinforcement"]["steel"],
            ),
        "steel_compression_with_buckling": report_section(
                "Acero longitudinal en compresion con pandeo",
                "Parametros de degradacion por pandeo del acero longitudinal.",
                {
                    "s_over_db": report_equation("s / d_b", steel_models["steel_compression_with_buckling"]["s_over_db"], "-"),
                    "epsilon_buckling": report_equation(
                        "0.10 - 0.0146*(s/d_b) + 0.00062*(s/d_b)^2",
                        steel_models["steel_compression_with_buckling"]["eps_buckling"],
                        "m/m",
                    ),
                    "fbb_over_fy": report_equation(
                        "1.105 - 0.0211*(s/d_b) - 0.00517*(s/d_b)^2",
                        steel_models["steel_compression_with_buckling"]["fbb_over_fy"],
                        "-",
                    ),
                    "fbb": report_value(steel_models["steel_compression_with_buckling"]["fbb_mpa"], "MPa"),
                },
                inputs_used={
                    "tie_spacing": config["transverse_reinforcement"]["spacing"],
                    "longitudinal_bar_diameter": config["longitudinal_reinforcement"]["diameter"],
                    "fy": config["longitudinal_reinforcement"]["steel"]["fy"],
                    "compression_buckling": config["longitudinal_reinforcement"]["steel"]["compression_buckling"],
                },
            ),
        "welded_wire_mesh": report_section(
                "Malla electrosoldada",
                "Parametros mecanicos seleccionados para la malla electrosoldada de comparacion.",
                {
                    "diameter": report_value(mesh_model["diameter_mm"], "mm"),
                    "fy": report_value(mesh_model["fy_mpa"], "MPa"),
                    "fu": report_value(mesh_model["fu_mpa"], "MPa"),
                    "epsilon_u": report_value(mesh_model["epsilon_u"], "m/m"),
                },
                inputs_used=config["welded_wire_mesh"],
        ),
    }


def build_initial_results(
    config: dict[str, Any],
    output_dirs: dict[str, Path],
    *,
    geometry_summary: dict[str, object],
    confinement_parameters: dict[str, object],
    curves: dict[str, dict[str, object]],
    metrics: list[dict[str, object]],
    generated_files: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    """Build the Etapa 1 result dictionary."""

    return {
        "stage_id": config["stage_id"],
        "title": config["title"],
        "status": "completed",
        "message": "Configuracion leida, curvas generadas y salidas exportadas.",
        "source_pdf": _resolve_source_pdf(config),
        "inputs_summary": {
            "units": config["units"],
            "section": config["section"],
            "concrete": config["concrete"],
            "longitudinal_reinforcement": config["longitudinal_reinforcement"],
            "transverse_reinforcement": config["transverse_reinforcement"],
            "welded_wire_mesh": config["welded_wire_mesh"],
            "model_inputs": config["model_inputs"],
        },
        "output_directories": output_dirs,
        "assumptions": list(config["section"].get("assumptions", []))
        + list(confinement_parameters.get("assumptions", [])),
        "geometry": geometry_summary,
        "confinement_parameters": confinement_parameters,
        "model_parameters": {name: curve.get("parameters", {}) for name, curve in curves.items()},
        "metrics": metrics,
        "generated_files": generated_files,
        "warnings": warnings,
        "computed_results": {
            "confined_core_geometry": geometry_summary["confined_core"],
            "volumetric_reinforcement_ratio": confinement_parameters["rho_s"],
            "confinement_effectiveness_factor": confinement_parameters["ke"],
            "concrete_curves": list(name for name in curves if "concrete" in name or "mander" in name or "attard" in name),
            "steel_curves": [name for name in curves if "steel" in name],
            "mesh_curves": [name for name in curves if "mesh" in name],
            "comparative_metrics": metrics,
            "figures": [path for key, path in generated_files.items() if key.startswith("figure_")],
            "data_files": [path for key, path in generated_files.items() if key.startswith("data_")],
            "reports": [path for key, path in generated_files.items() if key.startswith("report_")],
        },
    }


def run(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_root: str | Path = "outputs",
) -> dict[str, Any]:
    """Read Etapa 1 configuration and prepare output directories.

    This stage flow reads inputs, calls mechanics models and exports organized
    stage artifacts.
    """

    result = prepare_stage_from_config(
        config_path,
        output_root=output_root,
        required_keys=REQUIRED_TOP_LEVEL_KEYS,
    )
    validate_stage_01_config(result["config"])

    config = result["config"]
    output_dirs = result["output_dirs"]
    geometry_summary, confinement_parameters = build_geometry_and_confinement(config)
    concrete_curves, steel_curves, mesh_curves = generate_material_curves(config, confinement_parameters)
    all_curves = {**concrete_curves, **steel_curves, **mesh_curves}
    metrics = calculate_curve_metrics_table(all_curves)

    data_dir = output_dirs["data"]
    figures_dir = output_dirs["figures"]
    reports_dir = output_dirs["reports"]

    generated_paths: dict[str, Path] = {}
    generated_paths["data_concrete_curves"] = write_csv_rows(curve_rows(concrete_curves), data_dir / "concrete_curves.csv")
    generated_paths["data_steel_curves"] = write_csv_rows(curve_rows(steel_curves), data_dir / "steel_curves.csv")
    generated_paths["data_mesh_curves"] = write_csv_rows(curve_rows(mesh_curves), data_dir / "mesh_curves.csv")
    generated_paths["data_curve_metrics"] = write_csv_rows(metrics, data_dir / "curve_metrics.csv")

    model_data_dir = data_dir / "models"
    for model_key, curve in all_curves.items():
        model_rows = curve_rows({model_key: curve})
        model_output_dir = model_data_dir / canonical_model_key(model_key)
        generated_paths[f"data_model_{model_key}_csv"] = write_csv_rows(
            model_rows,
            model_output_dir / f"{model_key}.csv",
        )
        generated_paths[f"data_model_{model_key}_xlsx"] = write_xlsx(
            model_rows,
            model_output_dir / f"{model_key}.xlsx",
            sheet_name=canonical_model_key(model_key)[:31],
        )

    generated_paths["figure_concrete"] = plot_stress_strain_curves(
        concrete_curves,
        figures_dir / "concrete_models_comparison.png",
        title="Comparación de modelos de concreto",
        subtitle=f"Columna {config['section']['width']:.0f} x {config['section']['height']:.0f} [mm] | f'co = {config['concrete']['f_co']} [MPa]",
        xlabel="Deformación unitaria, εc [mm/mm]",
        ylabel="Esfuerzo, fc [MPa]",
    )
    generated_paths["figure_steel_tension"] = plot_stress_strain_curves(
        {"steel_tension_mander": steel_curves["steel_tension_mander"]},
        figures_dir / "steel_tension_comparison.png",
        title="Acero longitudinal en tracción",
        subtitle=f"Barra #7 | fy medio = {config['longitudinal_reinforcement']['steel']['fy']} [MPa]",
        xlabel="Deformación unitaria de tracción, εs [mm/mm]",
        ylabel="Esfuerzo de tracción, fs [MPa]",
    )
    generated_paths["figure_steel_buckling"] = plot_stress_strain_curves(
        {
            "steel_compression_no_buckling": steel_curves["steel_compression_no_buckling"],
            "steel_compression_with_buckling": steel_curves["steel_compression_with_buckling"],
        },
        figures_dir / "steel_compression_buckling.png",
        title="Acero longitudinal en compresión",
        subtitle="Comparación con y sin degradación por pandeo | flejes #4 @ 100 [mm]",
        xlabel="Deformación unitaria de compresión, εs [mm/mm]",
        ylabel="Esfuerzo de compresión, fs [MPa]",
    )
    generated_paths["figure_mesh"] = plot_stress_strain_curves(
        mesh_curves,
        figures_dir / "welded_wire_mesh.png",
        title="Malla electrosoldada",
        subtitle=f"Diámetro seleccionado = {config['welded_wire_mesh']['default_diameter']} [mm]",
        xlabel="Deformación unitaria de tracción, εs [mm/mm]",
        ylabel="Esfuerzo de tracción, fs [MPa]",
    )
    generated_paths["figure_core_sketch"] = plot_confined_core_sketch(
        geometry_summary,
        figures_dir / "confined_core_sketch.png",
        title="Seccion base de la Etapa 1",
    )
    model_figures_dir = figures_dir / "models"
    for curve_name, curve in all_curves.items():
        model_key = canonical_model_key(curve_name)
        plot_text = model_plot_text(model_key)
        generated_paths[f"figure_model_{model_key}"] = plot_single_model_curve_with_notable_points(
            curve_name,
            curve,
            model_figures_dir / f"{model_key}.png",
            title=plot_text["title"],
            subtitle=plot_text["subtitle"],
            xlabel=plot_text["xlabel"],
            ylabel=plot_text["ylabel"],
        )

    warnings = []
    for curve in all_curves.values():
        warnings.extend(str(warning) for warning in curve.get("warnings", []))

    calculated_parameters_report = build_calculated_parameters_report(
        config,
        geometry_summary=geometry_summary,
        confinement_parameters=confinement_parameters,
        curves=all_curves,
    )
    for old_global_report in (
        reports_dir / "stage_01_calculated_parameters.yaml",
        reports_dir / "stage_01_report.pdf",
    ):
        if old_global_report.exists():
            old_global_report.unlink()
    old_document_root = reports_dir / "documento"
    if old_document_root.exists():
        shutil.rmtree(old_document_root)
    old_model_reports_dir = reports_dir / "models"
    if old_model_reports_dir.exists():
        shutil.rmtree(old_model_reports_dir)

    constitutive_model_reports = split_constitutive_model_reports(calculated_parameters_report)
    for model_key, model_report in constitutive_model_reports.items():
        model_report_dir = reports_dir / model_key
        generated_paths[f"report_model_{model_key}_yaml"] = write_yaml_result(
            model_report,
            model_report_dir / f"{model_key}.yaml",
        )
    mander_unconfined_yaml = generated_paths["report_model_mander_classic_unconfined_concrete_yaml"]
    mander_unconfined_report = load_yaml_config(mander_unconfined_yaml)
    document_dir = reports_dir / "mander_classic_unconfined_concrete"
    document_assets_dir = document_dir / "assets"
    document_assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        figures_dir / "models" / "mander_classic_unconfined_concrete.png",
        document_assets_dir / "mander_classic_unconfined_concrete.png",
    )
    mander_unconfined_qmd = write_quarto_source(
        build_mander_unconfined_quarto_document(mander_unconfined_report),
        document_dir / "mander_classic_unconfined_concrete_memoria.qmd",
    )
    generated_paths["report_document_mander_classic_unconfined_concrete_qmd"] = mander_unconfined_qmd
    generated_paths["report_document_mander_classic_unconfined_concrete_pdf"] = render_quarto_pdf(mander_unconfined_qmd)

    generated_files = {key: str(path) for key, path in generated_paths.items()}
    initial_results = build_initial_results(
        config,
        output_dirs,
        geometry_summary=geometry_summary,
        confinement_parameters=confinement_parameters,
        curves=all_curves,
        metrics=metrics,
        generated_files=generated_files,
        warnings=warnings,
    )
    results_path = stage_results_json_path(output_dirs)
    generated_files["data_results_json"] = str(results_path)
    initial_results["generated_files"] = generated_files
    write_json_result(initial_results, results_path)

    result["results"] = initial_results
    result["results_path"] = results_path
    result["generated_files"] = generated_files
    result["warnings"] = warnings
    return result




"""Quarto memories for Stage 1 seismic hazard reports."""

from __future__ import annotations

import csv
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from structurelab_pbd_rc.io.read_config import load_yaml_config
from structurelab_pbd_rc.reports.export_quarto import render_quarto_pdf, write_quarto_source


LEVEL_LABELS = {
    "service": "Servicio",
    "design": "Diseno",
    "maximum_considered": "Maximo considerado",
}


def _format_number(value: float, digits: int = 6) -> str:
    """Return compact report-ready numeric text."""

    return f"{float(value):.{digits}g}"


def _spanish_date(today: date | None = None) -> str:
    """Return a Spanish date label."""

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


def _copy_report_assets(generated_files: dict[str, Any], assets_dir: Path) -> dict[str, str]:
    """Copy generated figures to the document assets folder."""

    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_paths: dict[str, str] = {}
    for key, raw_path in generated_files.items():
        if not key.endswith("_figure"):
            continue
        source = Path(raw_path)
        if not source.exists():
            continue
        target = assets_dir / source.name
        shutil.copyfile(source, target)
        asset_paths[key] = f"assets/{target.name}"
    return asset_paths


def _artifact_prefix(case_id: str) -> str:
    """Return the generated-files key prefix used by one Stage 1 case."""

    if case_id == "case_01_nsr10":
        return "case_01"
    if case_id == "case_02_sgc_ccp14":
        return "case_02"
    raise ValueError(f"Unsupported Stage 1 case_id: {case_id}")


def _spectrum_csv_key(case_id: str) -> str:
    """Return the generated-files key that points to the spectrum CSV."""

    return f"{_artifact_prefix(case_id)}_spectra_csv"


def _read_spectrum_rows_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Read spectrum rows through the CSV path stored in the report YAML."""

    case_id = str(report["case_id"])
    generated_files = report["generated_files"]
    csv_path = Path(generated_files[_spectrum_csv_key(case_id)])
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _metadata_rows(report: dict[str, Any]) -> str:
    """Return markdown rows for the report metadata table."""

    inputs = report["datos_de_entrada"]
    seismic = inputs["hazard"]["seismic"]
    period_range = seismic["period_range"]
    units = inputs["units"]
    rows = [
        ("Etapa", report["stage_id"]),
        ("Caso", report["case_id"]),
        ("Titulo", report["title"]),
        ("Unidad de periodo", f"[{units['period']}]"),
        ("Unidad de aceleracion espectral", f"[{units['spectral_acceleration']}]"),
        (
            "Rango de periodos",
            (
                f"{_format_number(period_range['start'])} a {_format_number(period_range['end'])} "
                f"[s], paso = {_format_number(period_range['step'])} [s]"
            ),
        ),
    ]
    return "\n".join(f"| {name} | {value} |" for name, value in rows)


def _input_rows_nsr10(report: dict[str, Any]) -> str:
    """Return NSR-10 input rows."""

    seismic = report["datos_de_entrada"]["hazard"]["seismic"]
    parameters = seismic["nsr10_parameters"]
    levels = seismic["hazard_levels"]
    rows = [
        ("Codigo fuente", seismic["source"].get("code", "NSR-10")),
        ("Descripcion", seismic["source"].get("description", "")),
        ("Perfil de suelo", parameters["soil_profile"]),
        ("$A_a$", _format_number(parameters["Aa"])),
        ("$A_v$", _format_number(parameters["Av"])),
        ("$F_a$", _format_number(parameters["Fa"])),
        ("$F_v$", _format_number(parameters["Fv"])),
        ("$I$", _format_number(parameters["importance_factor"])),
        ("Factor servicio, Tr = 31 anos", _format_number(levels["service"]["scale_factor"])),
        ("Factor diseno, Tr = 475 anos", _format_number(levels["design"]["scale_factor"])),
        (
            "Factor maximo considerado, Tr = 2500 anos",
            _format_number(levels["maximum_considered"]["scale_factor"]),
        ),
    ]
    return "\n".join(f"| {name} | {value} |" for name, value in rows)


def _input_rows_ccp14(report: dict[str, Any]) -> str:
    """Return CCP-14 input rows."""

    seismic = report["datos_de_entrada"]["hazard"]["seismic"]
    source = seismic["source"]
    site = seismic["site"]
    rows = [
        ("Proveedor de amenaza", source.get("hazard_provider", "")),
        ("Forma espectral", source.get("spectral_shape_code", "CCP-14")),
        ("Seccion de referencia", source.get("spectral_shape_section", "")),
        ("Perfil de suelo", site["profile"]),
    ]
    for level_key, level in seismic["hazard_levels"].items():
        label = LEVEL_LABELS.get(level_key, str(level_key))
        rows.extend(
            [
                (f"{label}: periodo de retorno", f"{int(level['return_period_years'])} anos"),
                (f"{label}: PGA", f"{_format_number(level['PGA'])} [g]"),
                (f"{label}: Sa(0.2 s)", f"{_format_number(level['Sa_0_2'])} [g]"),
                (f"{label}: Sa(1.0 s)", f"{_format_number(level['Sa_1_0'])} [g]"),
            ]
        )
    return "\n".join(f"| {name} | {value} |" for name, value in rows)


def _parameter_rows_nsr10(report: dict[str, Any]) -> str:
    """Return NSR-10 output parameter rows."""

    params = report["datos_de_salida"]["transition_parameters"]
    rows = [
        ("$T_0$", f"{_format_number(params['T0'])} [s]", "$0.1 A_v F_v/(A_a F_a)$"),
        ("$T_C$", f"{_format_number(params['Tc'])} [s]", "$0.48 A_v F_v/(A_a F_a)$"),
        ("$T_L$", f"{_format_number(params['TL'])} [s]", "$2.4 F_v$"),
        ("Meseta", f"{_format_number(params['Sa_plateau'])} [g]", "$2.5 A_a F_a I$"),
    ]
    return "\n".join(f"| {name} | {value} | {equation} |" for name, value, equation in rows)


def _parameter_rows_ccp14(report: dict[str, Any]) -> str:
    """Return CCP-14 output parameter rows."""

    rows = []
    for params in report["datos_de_salida"]["parameters_by_return_period"]:
        rows.append(
            "| "
            f"{int(params['return_period_years'])} | "
            f"{_format_number(params['Fpga'])} | "
            f"{_format_number(params['Fa'])} | "
            f"{_format_number(params['Fv'])} | "
            f"{_format_number(params['As'])} | "
            f"{_format_number(params['SDS'])} | "
            f"{_format_number(params['SD1'])} | "
            f"{_format_number(params['T0'])} | "
            f"{_format_number(params['Ts'])} |"
        )
    return "\n".join(rows)


def _max_row(rows: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    """Return the row with maximum spectral acceleration for a series."""

    return max(rows, key=lambda row: float(row[value_key]))


def _value_at_period(rows: list[dict[str, Any]], value_key: str, period: float) -> float:
    """Return the tabulated value nearest to a target period."""

    nearest = min(rows, key=lambda row: abs(float(row["period_s"]) - period))
    return float(nearest[value_key])


def _spectrum_summary_rows(rows: list[dict[str, Any]], series: list[tuple[str, str, int]]) -> str:
    """Return spectrum summary rows by hazard level."""

    output_rows = []
    for label, value_key, return_period in series:
        peak = _max_row(rows, value_key)
        output_rows.append(
            "| "
            f"{label} | "
            f"{return_period} | "
            f"{_format_number(_value_at_period(rows, value_key, 0.0))} | "
            f"{_format_number(_value_at_period(rows, value_key, 1.0))} | "
            f"{_format_number(float(peak[value_key]))} | "
            f"{_format_number(float(peak['period_s']))} |"
        )
    return "\n".join(output_rows)


def _etabs_file_rows(generated_files: dict[str, Any], key_prefix: str) -> str:
    """Return rows for ETABS text export files."""

    rows = []
    for level_key, label in LEVEL_LABELS.items():
        key = f"{key_prefix}_{level_key}_etabs_txt"
        if key not in generated_files:
            continue
        rows.append(f"| {label} | `{generated_files[key]}` |")
    return "\n".join(rows)


def _figure_block(asset_paths: dict[str, str], key: str, caption: str, *, width: str = "100%") -> str:
    """Return a Markdown figure block when the asset is available."""

    path = asset_paths.get(key)
    if not path:
        return ""
    return f"![{caption}]({path}){{width={width}}}"


def _nsr10_equations_block() -> str:
    """Return NSR-10 equations as display math."""

    return r"""
$$
T_0 = 0.1\frac{A_vF_v}{A_aF_a}
\qquad
T_C = 0.48\frac{A_vF_v}{A_aF_a}
\qquad
T_L = 2.4F_v
$$

$$
S_a(T)=
\begin{cases}
2.5A_aF_aI\left(0.4+0.6\dfrac{T}{T_0}\right), & 0 \leq T < T_0 \\
2.5A_aF_aI, & T_0 \leq T \leq T_C \\
\dfrac{1.2A_vF_vI}{T}, & T_C < T \leq T_L \\
\dfrac{1.2A_vF_vT_LI}{T^2}, & T > T_L
\end{cases}
$$
"""


def _ccp14_equations_block() -> str:
    """Return CCP-14 equations as display math."""

    return r"""
$$
A_s = F_{pga}PGA
\qquad
S_{DS}=F_aS_s
\qquad
S_{D1}=F_vS_1
$$

$$
T_s = \frac{S_{D1}}{S_{DS}}
\qquad
T_0 = 0.2T_s
$$

$$
C_{sm}(T)=
\begin{cases}
A_s + (S_{DS}-A_s)\dfrac{T}{T_0}, & 0 \leq T < T_0 \\
S_{DS}, & T_0 \leq T \leq T_s \\
\dfrac{S_{D1}}{T}, & T > T_s
\end{cases}
$$
"""


def build_stage_01_quarto_document(
    report: dict[str, Any],
    asset_paths: dict[str, str],
) -> str:
    """Build a Spanish Quarto memory from the Stage 1 report YAML."""

    case_id = str(report["case_id"])
    generated_files = report["generated_files"]
    spectrum_rows = _read_spectrum_rows_from_report(report)
    artifact_prefix = _artifact_prefix(case_id)
    if case_id == "case_01_nsr10":
        subtitle = "Caso NSR-10"
        input_rows = _input_rows_nsr10(report)
        parameter_header = "| Parametro | Valor | Ecuacion |\n|---|---:|---|"
        parameter_rows = _parameter_rows_nsr10(report)
        equations = _nsr10_equations_block()
        series = [
            ("Servicio", "Sa_servicio_31", 31),
            ("Diseno", "Sa_diseno_475", 475),
            ("Maximo considerado", "Sa_maximo_considerado_2500", 2500),
        ]
        key_prefix = "case_01_nsr10"
        overview_figure = _figure_block(asset_paths, "case_01_spectra_figure", "Espectros NSR-10 por nivel de amenaza.")
        individual_figures = "\n\n".join(
            block
            for block in (
                _figure_block(asset_paths, "case_01_service_spectrum_figure", "Espectro NSR-10 de servicio."),
                _figure_block(asset_paths, "case_01_design_spectrum_figure", "Espectro NSR-10 de diseno."),
                _figure_block(
                    asset_paths,
                    "case_01_maximum_considered_spectrum_figure",
                    "Espectro NSR-10 maximo considerado.",
                ),
            )
            if block
        )
    elif case_id == "case_02_sgc_ccp14":
        subtitle = "Caso SGC + CCP-14"
        input_rows = _input_rows_ccp14(report)
        parameter_header = (
            "| Tr [anos] | Fpga | Fa | Fv | As [g] | SDS [g] | SD1 [g] | T0 [s] | Ts [s] |\n"
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        parameter_rows = _parameter_rows_ccp14(report)
        equations = _ccp14_equations_block()
        series = [
            ("Servicio", "Sa_SGC_CCP14_31", 31),
            ("Diseno", "Sa_SGC_CCP14_475", 475),
            ("Maximo considerado", "Sa_SGC_CCP14_2500", 2500),
        ]
        key_prefix = "case_02_sgc_ccp14"
        overview_figure = _figure_block(asset_paths, "case_02_spectra_figure", "Espectros SGC + CCP-14 por nivel de amenaza.")
        individual_figures = "\n\n".join(
            block
            for block in (
                _figure_block(asset_paths, "case_02_service_spectrum_figure", "Espectro SGC + CCP-14 de servicio."),
                _figure_block(asset_paths, "case_02_design_spectrum_figure", "Espectro SGC + CCP-14 de diseno."),
                _figure_block(
                    asset_paths,
                    "case_02_maximum_considered_spectrum_figure",
                    "Espectro SGC + CCP-14 maximo considerado.",
                ),
            )
            if block
        )
    else:
        raise ValueError(f"Unsupported Stage 1 report case_id: {case_id}")

    summary_rows = _spectrum_summary_rows(spectrum_rows, series)
    etabs_rows = _etabs_file_rows(generated_files, key_prefix)
    report_yaml_key = f"{artifact_prefix}_report_yaml"
    spectra_csv_key = f"{artifact_prefix}_spectra_csv"
    spectra_xlsx_key = f"{artifact_prefix}_spectra_xlsx"

    return f"""---
title: "Memoria de calculo"
subtitle: "Etapa 1 - {subtitle}"
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

# Identificacion

Esta memoria resume los resultados de amenaza sismica de la Etapa 1. Los valores mostrados se consumen desde los resultados ya calculados por el workflow; este documento no recalcula el espectro.

| Campo | Valor |
|---|---|
{_metadata_rows(report)}

# Datos de entrada

| Dato | Valor |
|---|---:|
{input_rows}

# Ecuaciones usadas

{equations}

# Parametros calculados

{parameter_header}
{parameter_rows}

# Resumen de espectros

| Nivel | Tr [anos] | Sa(T=0) [g] | Sa(T=1.0 s) [g] | Sa maxima [g] | T en Sa maxima [s] |
|---|---:|---:|---:|---:|---:|
{summary_rows}

# Figuras

{overview_figure}

{individual_figures}

# Archivos para ETABS v22

Los archivos TXT se exportan sin encabezado y con dos columnas por linea: periodo `T` y aceleracion espectral `Sa`.
En ETABS v22 deben importarse como `From File`, con `Values are = Period vs Value` y `Header Lines to Skip = 0`.

| Nivel | Archivo |
|---|---|
{etabs_rows}

# Archivos asociados

- YAML del caso: `{generated_files.get(report_yaml_key, "")}`
- CSV de espectros: `{generated_files.get(spectra_csv_key, "")}`
- XLSX de espectros: `{generated_files.get(spectra_xlsx_key, "")}`
"""


def write_stage_01_pdf_report_from_yaml(report_yaml_path: str | Path) -> dict[str, Path]:
    """Write the Stage 1 Quarto source and PDF by consuming the report YAML."""

    yaml_path = Path(report_yaml_path)
    report = load_yaml_config(yaml_path)
    case_id = str(report["case_id"])
    generated_files = report["generated_files"]
    document_dir = yaml_path.parent / case_id
    assets_dir = document_dir / "assets"
    asset_paths = _copy_report_assets(generated_files, assets_dir)
    qmd_path = write_quarto_source(
        build_stage_01_quarto_document(report, asset_paths),
        document_dir / f"{case_id}_memoria.qmd",
    )
    pdf_path = render_quarto_pdf(qmd_path)
    return {
        f"{case_id}_report_qmd": qmd_path,
        f"{case_id}_report_pdf": pdf_path,
    }

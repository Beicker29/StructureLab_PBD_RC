"""Self-contained YAML and PDF reports for one Stage 2 material model."""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap
from typing import Any, Mapping

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def _wrapped_lines(label: str, value: Any, *, width: int = 88) -> list[str]:
    text = f"{label}: {value}"
    return wrap(text, width=width, subsequent_indent="  ") or [text]


def write_stage_02_pdf_report(
    payload: Mapping[str, Any],
    figure_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Write a compact PDF report without an external document renderer."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = payload["metrics"]
    calculated = payload["calculated_parameters"]
    metadata = payload["metadata"]
    lines = [
        str(payload["title"]),
        "",
        *_wrapped_lines("Project ID", payload["project_id"]),
        *_wrapped_lines("Case ID", payload["case_id"]),
        *_wrapped_lines("Material", metadata["material"]),
        *_wrapped_lines("Behavior", metadata["analysis_type"]),
        *_wrapped_lines("Model ID", metadata["model_id"]),
        *_wrapped_lines("Source JSON", metadata["source_json"]),
        "",
        "Response metrics",
        *_wrapped_lines("Point count", metrics["point_count"]),
        *_wrapped_lines(
            "Strain range",
            f"{metrics['strain_min']} to {metrics['strain_max']}",
        ),
        *_wrapped_lines(
            "Stress range [MPa]",
            f"{metrics['stress_min_mpa']} to {metrics['stress_max_mpa']}",
        ),
        *_wrapped_lines("Reversals", metrics["reversal_count"]),
        *_wrapped_lines("Failed points", metrics["failed_count"]),
        "",
        "Calculated parameters",
    ]
    preferred_parameters = (
        "s_over_db",
        "L_over_D",
        "rb",
        "yield_strain",
        "elastic_ultimate_strain",
        "residual_stress_mpa",
    )
    shown = False
    for key in preferred_parameters:
        if calculated.get(key) not in (None, ""):
            lines.extend(_wrapped_lines(key, calculated[key]))
            shown = True
    if not shown:
        lines.append("No additional scalar controls.")
    lines.extend(["", "Warnings"])
    warnings = payload.get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.extend(_wrapped_lines("-", warning))
    else:
        lines.append("None.")

    with PdfPages(path) as pdf:
        page = plt.figure(figsize=(8.5, 11.0), dpi=150)
        page.patch.set_facecolor("white")
        page.text(
            0.08,
            0.95,
            "\n".join(lines),
            ha="left",
            va="top",
            fontsize=9.0,
            color="#20262e",
            family="DejaVu Sans",
            linespacing=1.35,
        )
        page.text(
            0.92,
            0.035,
            "StructureLab_PBD_RC | Stage 2",
            ha="right",
            va="bottom",
            fontsize=7.5,
            color="#737b85",
        )
        pdf.savefig(page, facecolor="white")
        plt.close(page)

        response_figure = Path(figure_path)
        if response_figure.is_file():
            image = plt.imread(response_figure)
            figure_page = plt.figure(figsize=(11.0, 8.5), dpi=150)
            axis = figure_page.add_axes((0.03, 0.03, 0.94, 0.94))
            axis.imshow(image)
            axis.axis("off")
            pdf.savefig(figure_page, facecolor="white")
            plt.close(figure_page)
    return path

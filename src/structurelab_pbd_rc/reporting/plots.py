"""Professional plotting helpers for workshop reports."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd() / ".matplotlib_cache"))

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib.patches import Circle, Rectangle
from matplotlib.ticker import AutoMinorLocator, MaxNLocator


MODEL_LABELS = {
    "unconfined_concrete": "Concreto no confinado",
    "mander_classic": "Mander clasico",
    "mander_adjusted": "Mander ajustado",
    "attard_setunge_unconfined": "Attard-Setunge no confinado",
    "attard_setunge_confined": "Attard-Setunge confinado",
    "steel_tension": "Acero longitudinal - traccion",
    "steel_compression_no_buckling": "Compresion sin pandeo",
    "steel_compression_with_buckling": "Compresion con pandeo",
    "welded_wire_mesh": "Malla electrosoldada",
}

COLOR_CYCLE = [
    "#1f4e79",
    "#c43c2f",
    "#2f7d4f",
    "#7a4f9a",
    "#d79a2b",
    "#5b6670",
]

LINE_STYLES = ["-", "-", "-", "--", "-.", ":"]


def _display_name(model_name: str) -> str:
    """Return a reader-friendly model name."""

    return MODEL_LABELS.get(model_name, model_name.replace("_", " ").title())


def _style_axes(ax: Any) -> None:
    """Apply a restrained engineering-report style."""

    ax.set_facecolor("#fbfbf8")
    ax.grid(True, which="major", color="#d7d9d4", linewidth=0.8)
    ax.grid(True, which="minor", color="#eceee9", linewidth=0.5)
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.xaxis.set_major_locator(MaxNLocator(nbins=7))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=7))
    ax.tick_params(axis="both", colors="#30343b", labelsize=10)
    for spine in ax.spines.values():
        spine.set_color("#30343b")
        spine.set_linewidth(0.9)


def _annotate_peak(ax: Any, strain: list[float], stress: list[float], color: str) -> None:
    """Mark the peak point for a curve."""

    if not strain or not stress:
        return
    peak_index = max(range(len(stress)), key=lambda index: stress[index])
    peak_x = strain[peak_index]
    peak_y = stress[peak_index]
    ax.scatter([peak_x], [peak_y], s=28, color=color, edgecolor="white", linewidth=0.8, zorder=5)


def _trim_trailing_zero_failure(strain: list[float], stress: list[float]) -> tuple[list[float], list[float]]:
    """Remove artificial zero tails used to represent post-ultimate cutoff."""

    positive_indices = [index for index, value in enumerate(stress) if value > 1e-9]
    if not positive_indices:
        return strain, stress
    last_positive = positive_indices[-1]
    return strain[: last_positive + 1], stress[: last_positive + 1]


def plot_stress_strain_curves(
    curves: dict[str, dict[str, object]],
    path: str | Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    xlabel: str = "Deformacion unitaria, epsilon (m/m)",
    ylabel: str = "Esfuerzo, f (MPa)",
) -> Path:
    """Plot named stress-strain curves to a polished PNG."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10.8, 6.4), dpi=180)
    fig.patch.set_facecolor("white")
    _style_axes(ax)

    for index, (model_name, curve) in enumerate(curves.items()):
        strain = [float(value) for value in curve.get("strain", [])]
        stress = [float(value) for value in curve.get("stress", [])]
        strain, stress = _trim_trailing_zero_failure(strain, stress)
        color = COLOR_CYCLE[index % len(COLOR_CYCLE)]
        line_style = LINE_STYLES[index % len(LINE_STYLES)]
        ax.plot(
            strain,
            stress,
            label=_display_name(model_name),
            color=color,
            linestyle=line_style,
            linewidth=2.35,
            solid_capstyle="round",
        )
        _annotate_peak(ax, strain, stress, color)

    inferred_title = title or "Curvas esfuerzo-deformacion"
    ax.set_title(inferred_title, loc="left", fontsize=15, fontweight="bold", color="#222831", pad=16)
    if subtitle:
        ax.text(
            0.0,
            1.015,
            subtitle,
            transform=ax.transAxes,
            fontsize=10,
            color="#5d636b",
            va="bottom",
        )
    ax.set_xlabel(xlabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.set_ylabel(ylabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)

    ax.margins(x=0.015, y=0.08)
    legend = ax.legend(
        loc="best",
        frameon=True,
        facecolor="white",
        edgecolor="#d7d9d4",
        framealpha=0.96,
        fontsize=9,
        title="Modelo",
        title_fontsize=9,
    )
    legend.get_title().set_fontweight("bold")

    fig.text(
        0.99,
        0.015,
        "StructureLab_PBD_RC | Taller 1",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#7b828a",
    )
    fig.tight_layout(rect=(0.035, 0.04, 0.985, 0.94))
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def _add_dimension_label(ax: Any, text: str, xy: tuple[float, float], xytext: tuple[float, float]) -> None:
    """Add a dimension arrow and label."""

    ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        arrowprops={"arrowstyle": "<->", "color": "#30343b", "linewidth": 1.0},
        ha="center",
        va="center",
        fontsize=9,
        color="#30343b",
    )


def plot_confined_core_sketch(
    geometry_summary: dict[str, object],
    path: str | Path,
    *,
    title: str = "Croquis de seccion y nucleo confinado",
) -> Path:
    """Draw a polished section sketch with gross section, confined core and bars."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gross = geometry_summary["gross_section"]
    core = geometry_summary["confined_core"]
    reinforcement = geometry_summary["longitudinal_reinforcement"]
    cover_cm = float(geometry_summary["clear_cover_to_tie_cm"])
    width_cm = float(gross["width_cm"])
    height_cm = float(gross["height_cm"])
    core_width_cm = float(core["width_cm"])
    core_height_cm = float(core["height_cm"])
    bars_per_side = int(geometry_summary.get("longitudinal_bars_per_side", 5))
    bar_diameter_mm = float(reinforcement["bar_diameter_mm"])

    fig, ax = plt.subplots(figsize=(8.2, 8.2), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fbfbf8")
    ax.set_aspect("equal", adjustable="box")

    gross_x = -width_cm / 2.0
    gross_y = -height_cm / 2.0
    core_x = -core_width_cm / 2.0
    core_y = -core_height_cm / 2.0

    ax.add_patch(
        Rectangle(
            (gross_x, gross_y),
            width_cm,
            height_cm,
            facecolor="#edf2f0",
            edgecolor="#222831",
            linewidth=2.0,
            label="Seccion 75 x 75 cm",
        )
    )
    ax.add_patch(
        Rectangle(
            (core_x, core_y),
            core_width_cm,
            core_height_cm,
            facecolor="#f8e6df",
            edgecolor="#c43c2f",
            linewidth=2.0,
            label="Nucleo confinado",
        )
    )

    bar_radius_cm = max((bar_diameter_mm / 10.0) / 2.0, 0.7)
    bar_points: list[tuple[float, float]] = []
    for i in range(bars_per_side):
        t = i / max(bars_per_side - 1, 1)
        x = core_x + t * core_width_cm
        y = core_y + t * core_height_cm
        bar_points.extend([(x, core_y), (x, core_y + core_height_cm), (core_x, y), (core_x + core_width_cm, y)])
    unique_points = sorted(set((round(x, 6), round(y, 6)) for x, y in bar_points))
    for x, y in unique_points:
        ax.add_patch(
            Circle(
                (x, y),
                radius=bar_radius_cm,
                facecolor="#1f4e79",
                edgecolor="white",
                linewidth=0.9,
                zorder=4,
            )
        )

    _add_dimension_label(
        ax,
        f"{width_cm:.0f} cm",
        (-width_cm / 2.0, -height_cm / 2.0 - 7.0),
        (width_cm / 2.0, -height_cm / 2.0 - 7.0),
    )
    _add_dimension_label(
        ax,
        f"{height_cm:.0f} cm",
        (width_cm / 2.0 + 7.0, -height_cm / 2.0),
        (width_cm / 2.0 + 7.0, height_cm / 2.0),
    )

    ax.annotate(
        f"Recubrimiento libre = {cover_cm:.1f} cm",
        xy=(gross_x + cover_cm, gross_y + cover_cm),
        xytext=(gross_x + 4.0, gross_y - 13.0),
        arrowprops={"arrowstyle": "->", "color": "#7a4f9a", "linewidth": 1.2},
        fontsize=9,
        color="#30343b",
    )
    ax.text(
        0,
        core_y + core_height_cm + 4.5,
        f"Nucleo: {core_width_cm:.1f} x {core_height_cm:.1f} cm",
        ha="center",
        va="bottom",
        fontsize=10,
        fontweight="bold",
        color="#c43c2f",
    )
    ax.text(
        0,
        gross_y - 18.0,
        f"Refuerzo longitudinal: {int(reinforcement['bar_count'])} barras {reinforcement['bar_mark']}",
        ha="center",
        va="top",
        fontsize=10,
        color="#30343b",
    )

    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#222831", pad=14)
    ax.set_xlabel("Dimension x (cm)", fontsize=10, fontweight="bold", color="#30343b")
    ax.set_ylabel("Dimension y (cm)", fontsize=10, fontweight="bold", color="#30343b")
    ax.grid(True, color="#e3e5df", linewidth=0.7)
    ax.set_xlim(gross_x - 18.0, -gross_x + 18.0)
    ax.set_ylim(gross_y - 24.0, -gross_y + 14.0)
    ax.legend(
        loc="upper right",
        frameon=True,
        facecolor="white",
        edgecolor="#d7d9d4",
        framealpha=0.96,
        fontsize=9,
    )
    fig.text(
        0.99,
        0.015,
        "StructureLab_PBD_RC | Taller 1",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#7b828a",
    )
    fig.tight_layout(rect=(0.035, 0.04, 0.985, 0.96))
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path

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

from structurelab_pbd_rc.reports.model_reports import MODEL_LABELS, canonical_model_key


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

    model_key = canonical_model_key(model_name)
    return MODEL_LABELS.get(model_key, model_key.replace("_", " ").title())


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


def _stress_at_x(strain: list[float], stress: list[float], x_value: float) -> float:
    """Interpolate stress at a strain value from a generated curve."""

    if not strain or not stress:
        return 0.0
    if x_value <= strain[0]:
        return stress[0]
    if x_value >= strain[-1]:
        return stress[-1]
    for index in range(1, len(strain)):
        x0 = strain[index - 1]
        x1 = strain[index]
        if x0 <= x_value <= x1:
            y0 = stress[index - 1]
            y1 = stress[index]
            ratio = (x_value - x0) / max(x1 - x0, 1e-12)
            return y0 + ratio * (y1 - y0)
    return stress[-1]


def _notable_points(model_name: str, curve: dict[str, object]) -> list[dict[str, object]]:
    """Return notable points for a constitutive curve."""

    model_key = canonical_model_key(model_name)
    parameters = curve.get("parameters", {})
    if not isinstance(parameters, dict):
        return []
    strain = [float(value) for value in curve.get("strain", [])]
    stress = [float(value) for value in curve.get("stress", [])]
    points: list[dict[str, object]] = []

    def add(label: str, x_key: str, y_key: str | None = None) -> None:
        if x_key not in parameters:
            return
        x_value = float(parameters[x_key])
        y_value = (
            float(parameters[y_key])
            if y_key and y_key in parameters and parameters[y_key] is not None
            else _stress_at_x(strain, stress, x_value)
        )
        points.append({"label": label, "strain": x_value, "stress": y_value})

    if model_key == "mander_classic_unconfined_concrete":
        if "epsilon_peak" in parameters and "f_co_mpa" in parameters:
            fco = float(parameters["f_co_mpa"])
            eps_co = float(parameters["epsilon_peak"])
            points.append(
                {
                    "label": "(f'co, εco)",
                    "legend_label": f"Resistencia máxima (f'co: {fco:g} [MPa], εco: {eps_co:g} [mm/mm])",
                    "strain": eps_co,
                    "stress": fco,
                    "annotate": False,
                }
            )
        if {"ft_mpa", "Et_mpa", "epsilon_t"}.issubset(parameters):
            ft = float(parameters.get("ft_plot_mpa", parameters["ft_mpa"]))
            tensile_modulus = float(parameters["Et_mpa"])
            eps_t = float(parameters.get("epsilon_t_plot", parameters["epsilon_t"]))
            points.append(
                {
                    "label": "(ft, εt)",
                    "legend_label": (
                        f"Tracción (ft: {ft:.3g} [MPa], Et: {tensile_modulus:.0f} [MPa], "
                        f"εt: {eps_t:.3g} [mm/mm])"
                    ),
                    "strain": eps_t,
                    "stress": ft,
                    "annotate": False,
                }
            )
        if "epsilon_sp" in parameters:
            eps_sp = float(parameters["epsilon_sp"])
            points.append(
                {
                    "label": "Descascaramiento",
                    "legend_label": f"Descascaramiento (εsp: {eps_sp:g} [mm/mm])",
                    "strain": eps_sp,
                    "stress": _stress_at_x(strain, stress, eps_sp),
                    "annotate": False,
                }
            )
    elif model_key in {"mander_classic_confined_concrete", "mander_adjusted_confined_concrete"}:
        add("Pico confinado: f'cc", "eps_cc", "fcc_mpa")
        add("Última confinada", "eps_cu")
    elif model_key == "attard_setunge_unconfined_concrete":
        add("Resistencia máxima: f'co", "epsilon_peak", "f_peak_mpa")
        add("Control descendente: i_c", "epsilon_ic", "f_ic_mpa")
        add("Última", "epsilon_u")
    elif model_key == "attard_setunge_confined_concrete":
        add("Pico confinado: f'cc", "epsilon_peak", "f_peak_mpa")
        add("Punto i", "epsilon_i", "fi_mpa")
        add("Punto 2i", "epsilon_2i", "f_2i_mpa")
    elif model_key in {"steel_tension_mander", "steel_compression_no_buckling"}:
        add("Fluencia", "eps_y", "fy_mpa")
        add("Inicio de endurecimiento", "eps_sh")
        add("Última", "eps_su", "fu_mpa")
    elif model_key == "steel_compression_with_buckling":
        add("Fluencia", "eps_y", "fy_mpa")
        add("Inicio de pandeo", "eps_buckling", "fbb_mpa")
        add("Última degradada", "eps_u")
    elif model_key == "welded_wire_mesh":
        if "fy_mpa" in parameters and "Es_mpa" in parameters:
            eps_y = float(parameters["fy_mpa"]) / max(float(parameters["Es_mpa"]), 1e-12)
            points.append({"label": "Fluencia estimada", "strain": eps_y, "stress": float(parameters["fy_mpa"])})
        add("Última", "epsilon_u", "fu_mpa")

    unique_points: list[dict[str, object]] = []
    seen: set[tuple[str, float, float]] = set()
    for point in points:
        key = (str(point["label"]), round(float(point["strain"]), 10), round(float(point["stress"]), 8))
        if key not in seen:
            seen.add(key)
            unique_points.append(point)
    return unique_points


def _trim_trailing_zero_failure(strain: list[float], stress: list[float]) -> tuple[list[float], list[float]]:
    """Remove artificial zero tails used to represent post-ultimate cutoff."""

    positive_indices = [index for index, value in enumerate(stress) if value > 1e-9]
    if not positive_indices:
        return strain, stress
    last_positive = positive_indices[-1]
    return strain[: last_positive + 1], stress[: last_positive + 1]


def _curve_for_plot(model_name: str, curve: dict[str, object]) -> tuple[list[float], list[float]]:
    """Return curve arrays, preserving real zero endpoints where they are part of the model."""

    strain = [float(value) for value in curve.get("strain", [])]
    stress = [float(value) for value in curve.get("stress", [])]
    if canonical_model_key(model_name) == "mander_classic_unconfined_concrete":
        return strain, stress
    return _trim_trailing_zero_failure(strain, stress)


def plot_single_model_curve_with_notable_points(
    model_name: str,
    curve: dict[str, object],
    path: str | Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    xlabel: str = "Deformación unitaria, ε [mm/mm]",
    ylabel: str = "Esfuerzo, f [MPa]",
) -> Path:
    """Plot one constitutive curve with notable points marked and labeled."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    strain, stress = _curve_for_plot(model_name, curve)

    fig, ax = plt.subplots(figsize=(10.8, 6.4), dpi=180)
    fig.patch.set_facecolor("white")
    _style_axes(ax)

    curve_color = COLOR_CYCLE[0]
    ax.plot(
        strain,
        stress,
        label=_display_name(model_name),
        color=curve_color,
        linewidth=2.65,
        solid_capstyle="round",
    )

    marker_colors = ["#c43c2f", "#2f7d4f", "#7a4f9a", "#d79a2b", "#5b6670"]
    for index, point in enumerate(_notable_points(model_name, curve)):
        x_value = float(point["strain"])
        y_value = float(point["stress"])
        point_color = marker_colors[index % len(marker_colors)]
        label = str(point.get("legend_label", f"{point['label']} ({x_value:.5g}, {y_value:.3g} [MPa])"))
        ax.scatter(
            [x_value],
            [y_value],
            s=56,
            color=point_color,
            edgecolor="white",
            linewidth=1.0,
            zorder=6,
            label=label,
        )
        if bool(point.get("annotate", True)):
            x_offset = 14 if index % 2 == 0 else -18
            y_offset = 12 if index % 3 != 2 else -18
            ax.annotate(
                str(point["label"]),
                xy=(x_value, y_value),
                xytext=(x_offset, y_offset),
                textcoords="offset points",
                arrowprops={"arrowstyle": "->", "color": point_color, "linewidth": 0.9},
                fontsize=8.5,
                color="#30343b",
                ha="left" if x_offset > 0 else "right",
                va="bottom" if y_offset > 0 else "top",
            )

    inferred_title = title or _display_name(model_name)
    ax.set_title(inferred_title, loc="left", fontsize=15, fontweight="bold", color="#222831", pad=16)
    if subtitle:
        ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=10, color="#5d636b", va="bottom")
    ax.set_xlabel(xlabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.set_ylabel(ylabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.margins(x=0.02, y=0.10)
    legend = ax.legend(
        loc="best",
        frameon=True,
        facecolor="white",
        edgecolor="#d7d9d4",
        framealpha=0.96,
        fontsize=8.4,
        title="Curva y puntos notables",
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


def plot_stress_strain_curves(
    curves: dict[str, dict[str, object]],
    path: str | Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    xlabel: str = "Deformación unitaria, ε [mm/mm]",
    ylabel: str = "Esfuerzo, f [MPa]",
) -> Path:
    """Plot named stress-strain curves to a polished PNG."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10.8, 6.4), dpi=180)
    fig.patch.set_facecolor("white")
    _style_axes(ax)

    for index, (model_name, curve) in enumerate(curves.items()):
        strain, stress = _curve_for_plot(model_name, curve)
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

    inferred_title = title or "Curvas esfuerzo-deformación"
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
    title: str = "Croquis de sección y núcleo confinado",
) -> Path:
    """Draw a polished section sketch with gross section, confined core and bars."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gross = geometry_summary["gross_section"]
    core = geometry_summary["confined_core"]
    reinforcement = geometry_summary["longitudinal_reinforcement"]
    cover_mm = float(geometry_summary["clear_cover_to_tie_cm"]) * 10.0
    width_mm = float(gross["width_cm"]) * 10.0
    height_mm = float(gross["height_cm"]) * 10.0
    core_width_mm = float(core["width_cm"]) * 10.0
    core_height_mm = float(core["height_cm"]) * 10.0
    bars_per_side = int(geometry_summary.get("longitudinal_bars_per_side", 5))
    bar_diameter_mm = float(reinforcement["bar_diameter_mm"])

    fig, ax = plt.subplots(figsize=(8.2, 8.2), dpi=180)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fbfbf8")
    ax.set_aspect("equal", adjustable="box")

    gross_x = -width_mm / 2.0
    gross_y = -height_mm / 2.0
    core_x = -core_width_mm / 2.0
    core_y = -core_height_mm / 2.0

    ax.add_patch(
        Rectangle(
            (gross_x, gross_y),
            width_mm,
            height_mm,
            facecolor="#edf2f0",
            edgecolor="#222831",
            linewidth=2.0,
            label="Sección 750 x 750 [mm]",
        )
    )
    ax.add_patch(
        Rectangle(
            (core_x, core_y),
            core_width_mm,
            core_height_mm,
            facecolor="#f8e6df",
            edgecolor="#c43c2f",
            linewidth=2.0,
            label="Núcleo confinado",
        )
    )

    bar_radius_mm = max(bar_diameter_mm / 2.0, 7.0)
    bar_points: list[tuple[float, float]] = []
    for i in range(bars_per_side):
        t = i / max(bars_per_side - 1, 1)
        x = core_x + t * core_width_mm
        y = core_y + t * core_height_mm
        bar_points.extend([(x, core_y), (x, core_y + core_height_mm), (core_x, y), (core_x + core_width_mm, y)])
    unique_points = sorted(set((round(x, 6), round(y, 6)) for x, y in bar_points))
    for x, y in unique_points:
        ax.add_patch(
            Circle(
                (x, y),
                radius=bar_radius_mm,
                facecolor="#1f4e79",
                edgecolor="white",
                linewidth=0.9,
                zorder=4,
            )
        )

    _add_dimension_label(
        ax,
        f"{width_mm:.0f} [mm]",
        (-width_mm / 2.0, -height_mm / 2.0 - 70.0),
        (width_mm / 2.0, -height_mm / 2.0 - 70.0),
    )
    _add_dimension_label(
        ax,
        f"{height_mm:.0f} [mm]",
        (width_mm / 2.0 + 70.0, -height_mm / 2.0),
        (width_mm / 2.0 + 70.0, height_mm / 2.0),
    )

    ax.annotate(
        f"Recubrimiento libre = {cover_mm:.0f} [mm]",
        xy=(gross_x + cover_mm, gross_y + cover_mm),
        xytext=(gross_x + 40.0, gross_y - 130.0),
        arrowprops={"arrowstyle": "->", "color": "#7a4f9a", "linewidth": 1.2},
        fontsize=9,
        color="#30343b",
    )
    ax.text(
        0,
        core_y + core_height_mm + 45.0,
        f"Núcleo: {core_width_mm:.0f} x {core_height_mm:.0f} [mm]",
        ha="center",
        va="bottom",
        fontsize=10,
        fontweight="bold",
        color="#c43c2f",
    )
    ax.text(
        0,
        gross_y - 180.0,
        f"Refuerzo longitudinal: {int(reinforcement['bar_count'])} barras {reinforcement['bar_mark']}",
        ha="center",
        va="top",
        fontsize=10,
        color="#30343b",
    )

    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#222831", pad=14)
    ax.set_xlabel("Dimensión x [mm]", fontsize=10, fontweight="bold", color="#30343b")
    ax.set_ylabel("Dimensión y [mm]", fontsize=10, fontweight="bold", color="#30343b")
    ax.grid(True, color="#e3e5df", linewidth=0.7)
    ax.set_xlim(gross_x - 180.0, -gross_x + 180.0)
    ax.set_ylim(gross_y - 240.0, -gross_y + 140.0)
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


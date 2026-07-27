"""Professional plotting helpers for stage reports."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "structurelab_pbd_rc_matplotlib_cache"))

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator, MaxNLocator


COLOR_CYCLE = [
    "#1f4e79",
    "#c43c2f",
    "#2f7d4f",
    "#7a4f9a",
    "#d79a2b",
    "#5b6670",
]

LINE_STYLES = ["-", "-", "-", "--", "-.", ":"]

MOMENT_CURVATURE_EXTERNAL_LEGEND_RECT = (0.035, 0.055, 0.70, 0.94)


def _display_name(model_name: str) -> str:
    """Return a reader-friendly model name."""

    return model_name.replace("_", " ").title()


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


def _add_external_moment_curvature_legend(
    ax: Any,
    *,
    handles: list[Any] | None = None,
    loc: str,
    anchor_y: float,
    title: str,
    fontsize: float,
    title_fontsize: float,
) -> Any:
    """Place a moment-curvature legend outside the plotting area."""

    legend_kwargs: dict[str, Any] = {
        "loc": loc,
        "bbox_to_anchor": (1.015, anchor_y),
        "borderaxespad": 0.0,
        "frameon": True,
        "facecolor": "white",
        "edgecolor": "#d7d9d4",
        "framealpha": 0.97,
        "fontsize": fontsize,
        "title": title,
        "title_fontsize": title_fontsize,
    }
    if handles is not None:
        legend_kwargs["handles"] = handles

    legend = ax.legend(**legend_kwargs)
    legend.get_title().set_fontweight("bold")
    legend.set_in_layout(False)
    return legend


def plot_response_spectra(
    rows: list[dict[str, Any]],
    path: str | Path,
    *,
    period_key: str,
    series: list[dict[str, str]],
    title: str,
    subtitle: str,
    ylabel: str = "Aceleracion espectral, Sa [g]",
) -> Path:
    """Plot one or more response spectra using the project report style."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    periods = [float(row[period_key]) for row in rows]

    fig, ax = plt.subplots(figsize=(11.4, 6.8), dpi=190)
    fig.patch.set_facecolor("white")
    _style_axes(ax)

    for index, item in enumerate(series):
        key = item["key"]
        label = item["label"]
        values = [float(row[key]) for row in rows]
        ax.plot(
            periods,
            values,
            label=label,
            color=COLOR_CYCLE[index % len(COLOR_CYCLE)],
            linestyle=LINE_STYLES[index % len(LINE_STYLES)],
            linewidth=2.8,
            solid_capstyle="round",
        )

    ax.set_xlabel("Periodo, T [s]", fontsize=11.5, fontweight="bold", color="#30343b")
    ax.set_ylabel(ylabel, fontsize=11.5, fontweight="bold", color="#30343b")
    ax.set_title(title, loc="left", fontsize=17, fontweight="bold", color="#24303a", pad=16)
    ax.text(
        0.0,
        1.01,
        subtitle,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=10.5,
        color="#5b6670",
    )
    legend = ax.legend(
        loc="upper right",
        frameon=True,
        framealpha=0.95,
        facecolor="white",
        edgecolor="#d7d9d4",
        fontsize=9.2,
        title="Nivel de amenaza",
    )
    legend.get_title().set_fontweight("bold")
    ax.margins(x=0.01, y=0.08)
    fig.text(0.985, 0.025, "StructureLab_PBD_RC | Etapa 1", ha="right", va="bottom", fontsize=8, color="#808891")
    fig.tight_layout(rect=(0, 0.04, 1, 0.98))
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_response_spectrum_with_notable_points(
    rows: list[dict[str, Any]],
    path: str | Path,
    *,
    period_key: str,
    value_key: str,
    title: str,
    subtitle: str,
    notable_points: list[dict[str, Any]],
    ylabel: str = "Aceleracion espectral, Sa [g]",
    curve_color: str = COLOR_CYCLE[0],
) -> Path:
    """Plot one response spectrum with its notable points."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    periods = [float(row[period_key]) for row in rows]
    values = [float(row[value_key]) for row in rows]

    fig, ax = plt.subplots(figsize=(11.4, 6.8), dpi=190)
    fig.patch.set_facecolor("white")
    _style_axes(ax)

    ax.plot(
        periods,
        values,
        color=curve_color,
        linewidth=3.0,
        solid_capstyle="round",
        label="Espectro elastico",
    )
    ax.fill_between(periods, values, color=curve_color, alpha=0.075)

    marker_colors = ["#c43c2f", "#2f7d4f", "#7a4f9a", "#d79a2b", "#5b6670"]
    for index, point in enumerate(notable_points):
        period = float(point["period"])
        value = float(point["value"])
        color = marker_colors[index % len(marker_colors)]
        label = str(point.get("legend_label", f"{point['label']}: T = {period:.4g} [s], Sa = {value:.4g} [g]"))
        ax.axvline(period, color=color, linestyle=":", linewidth=1.0, alpha=0.55)
        ax.scatter(
            [period],
            [value],
            s=72,
            color=color,
            edgecolor="white",
            linewidth=1.1,
            zorder=6,
            label=label,
        )
        if bool(point.get("annotate", False)):
            x_offset = 26 if period <= min(periods) + 1e-12 else 14 if index % 2 == 0 else -16
            y_offset = 18 if value >= max(values) * 0.92 else 14 if index % 3 != 2 else -20
            ax.annotate(
                str(point["label"]),
                xy=(period, value),
                xytext=(x_offset, y_offset),
                textcoords="offset points",
                arrowprops={"arrowstyle": "->", "color": color, "linewidth": 0.9},
                fontsize=8.5,
                color="#30343b",
                ha="left" if x_offset > 0 else "right",
                va="bottom" if y_offset > 0 else "top",
            )

    ax.set_xlabel("Periodo, T [s]", fontsize=11.5, fontweight="bold", color="#30343b")
    ax.set_ylabel(ylabel, fontsize=11.5, fontweight="bold", color="#30343b")
    ax.set_title(title, loc="left", fontsize=17, fontweight="bold", color="#24303a", pad=16)
    ax.text(
        0.0,
        1.01,
        subtitle,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=10.5,
        color="#5b6670",
    )
    x_min = min(periods)
    x_max = max(periods)
    x_span = max(x_max - x_min, 1e-9)
    notable_values = [float(point["value"]) for point in notable_points]
    y_min = min([0.0, *values, *notable_values])
    y_max = max([*values, *notable_values])
    y_span = max(y_max - y_min, 1e-9)
    ax.set_xlim(x_min - 0.055 * x_span, x_max + 0.015 * x_span)
    ax.set_ylim(y_min - 0.08 * y_span, y_max + 0.16 * y_span)
    legend = ax.legend(
        loc="upper right",
        frameon=True,
        framealpha=0.96,
        facecolor="white",
        edgecolor="#d7d9d4",
        fontsize=8.2,
        title="Puntos notables",
        title_fontsize=9,
    )
    legend.get_title().set_fontweight("bold")
    fig.text(0.985, 0.025, "StructureLab_PBD_RC | Etapa 1", ha="right", va="bottom", fontsize=8, color="#808891")
    fig.tight_layout(rect=(0, 0.04, 1, 0.98))
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def _annotate_peak(ax: Any, strain: list[float], stress: list[float], color: str) -> None:
    """Mark the largest stress magnitude for a curve."""

    if not strain or not stress:
        return
    peak_index = max(range(len(stress)), key=lambda index: abs(stress[index]))
    peak_x = strain[peak_index]
    peak_y = stress[peak_index]
    ax.scatter([peak_x], [peak_y], s=28, color=color, edgecolor="white", linewidth=0.8, zorder=5)


def _notable_points(curve: dict[str, object]) -> list[dict[str, object]]:
    """Return explicitly supplied notable points for a constitutive curve."""

    raw_points = curve.get("notable_points", [])
    if not isinstance(raw_points, list):
        return []
    return [
        point
        for point in raw_points
        if isinstance(point, dict) and {"label", "strain", "stress"}.issubset(point)
    ]


def _curve_for_plot(curve: dict[str, object]) -> tuple[list[float], list[float]]:
    """Return numeric strain and stress arrays supplied by a model."""

    return (
        [float(value) for value in curve.get("strain", [])],
        [float(value) for value in curve.get("stress", [])],
    )


def plot_single_model_curve_with_notable_points(
    model_name: str,
    curve: dict[str, object],
    path: str | Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    xlabel: str = "Deformacion unitaria, epsilon [mm/mm]",
    ylabel: str = "Esfuerzo, f [MPa]",
) -> Path:
    """Plot one constitutive curve with notable points marked and labeled."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    strain, stress = _curve_for_plot(curve)

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
    for index, point in enumerate(_notable_points(curve)):
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
        "StructureLab_PBD_RC | Etapa 2",
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
    xlabel: str = "Deformacion unitaria, epsilon [mm/mm]",
    ylabel: str = "Esfuerzo, f [MPa]",
) -> Path:
    """Plot named stress-strain curves to a polished PNG."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10.8, 6.4), dpi=180)
    fig.patch.set_facecolor("white")
    _style_axes(ax)

    for index, (model_name, curve) in enumerate(curves.items()):
        strain, stress = _curve_for_plot(curve)
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
        "StructureLab_PBD_RC | Etapa 2",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#7b828a",
    )
    fig.tight_layout(rect=(0.035, 0.04, 0.985, 0.94))
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def plot_uniaxial_response_rows(
    case_rows: dict[str, list[dict[str, Any]]],
    path: str | Path,
    *,
    title: str,
    subtitle: str,
) -> Path:
    """Plot precomputed uniaxial response rows without material calculations."""

    curves = {
        case_id: {
            "strain": [float(row["strain"]) for row in rows],
            "stress": [float(row["stress_mpa"]) for row in rows],
        }
        for case_id, rows in case_rows.items()
    }
    return plot_stress_strain_curves(curves, path, title=title, subtitle=subtitle)


def _signed_point_parameters(result: dict[str, object]) -> dict[str, float]:
    """Return signed notable M-phi parameters for plotting."""

    parameters = result.get("parameters", {})
    if not isinstance(parameters, dict):
        return {}
    bilinear_curve = result.get("bilinear_curve", [])
    sign = 1.0
    if isinstance(bilinear_curve, list) and len(bilinear_curve) >= 3:
        ultimate_phi = float(bilinear_curve[2]["phi"])
        if ultimate_phi < 0.0:
            sign = -1.0
    return {
        "My": sign * float(parameters["My"]),
        "phi_y": sign * float(parameters["phi_y"]),
        "Mu": sign * float(parameters["Mu"]),
        "phi_u": sign * float(parameters["phi_u"]),
        "M_60My": sign * float(parameters["M_60My"]),
        "phi_60My": sign * float(parameters["phi_60My"]),
    }


def _is_visible_moment_curvature_point(result: dict[str, object], phi_value: float) -> bool:
    """Return whether a notable point should be displayed in a possibly cut plot."""

    limit = result.get("visible_phi_abs_limit")
    if limit is None:
        return True
    return abs(phi_value) <= float(limit) + 1e-12


def _cyclic_cut_point_for_plot(result: dict[str, object]) -> tuple[float, float] | None:
    """Return the signed cyclic endpoint when a plot has been visually cut."""

    cut_point = result.get("cyclic_cut_point")
    if not isinstance(cut_point, dict):
        return None
    return float(cut_point["phi"]), float(cut_point["moment"])


def _finish_moment_curvature_plot(
    fig: Any,
    ax: Any,
    output_path: Path,
    *,
    title: str,
    subtitle: str | None,
    xlabel: str,
    ylabel: str,
    legend_title: str,
) -> Path:
    """Apply shared layout to moment-curvature figures."""

    ax.axhline(0.0, color="#30343b", linewidth=0.8)
    ax.axvline(0.0, color="#30343b", linewidth=0.8)
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#222831", pad=16)
    if subtitle:
        ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=10, color="#5d636b", va="bottom")
    ax.set_xlabel(xlabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.set_ylabel(ylabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.margins(x=0.04, y=0.10)
    legend = ax.legend(
        loc="best",
        frameon=True,
        facecolor="white",
        edgecolor="#d7d9d4",
        framealpha=0.96,
        fontsize=8.2,
        title=legend_title,
        title_fontsize=9,
    )
    legend.get_title().set_fontweight("bold")
    fig.text(
        0.99,
        0.015,
        "StructureLab_PBD_RC | Etapa 3",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#7b828a",
    )
    fig.tight_layout(rect=(0.035, 0.04, 0.985, 0.94))
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def plot_moment_curvature_real_curves(
    curve_results: list[dict[str, object]],
    path: str | Path,
    *,
    title: str = "Diagrama momento-curvatura",
    subtitle: str = "Curvas reales importadas desde Excel",
    xlabel: str = "Curvatura, phi [1/m]",
    ylabel: str = "Momento, M [kN-m]",
) -> Path:
    """Plot actual moment-curvature curves."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11.2, 6.6), dpi=180)
    fig.patch.set_facecolor("white")
    _style_axes(ax)

    for index, result in enumerate(curve_results):
        curve_id = str(result["curve_id"])
        curve_name = str(result.get("name", curve_id))
        color = COLOR_CYCLE[index % len(COLOR_CYCLE)]
        actual_curve = result["actual_curve"]
        if not isinstance(actual_curve, list):
            continue

        actual_phi = [float(point["phi"]) for point in actual_curve]
        actual_moment = [float(point["moment"]) for point in actual_curve]

        ax.plot(
            actual_phi,
            actual_moment,
            color=color,
            linewidth=2.35,
            label=curve_name,
        )
        cyclic_cut = _cyclic_cut_point_for_plot(result)
        if cyclic_cut is not None:
            phi_cut, moment_cut = cyclic_cut
            ax.scatter(
                [phi_cut],
                [moment_cut],
                s=72,
                color="#d79a2b",
                edgecolor="white",
                linewidth=1.0,
                zorder=6,
                label=f"{curve_name} - Mu ciclico: {moment_cut:.3g} [kN-m], phi_uc: {phi_cut:.4g} [1/m]",
            )

    return _finish_moment_curvature_plot(
        fig,
        ax,
        output_path,
        title=title,
        subtitle=subtitle,
        xlabel=xlabel,
        ylabel=ylabel,
        legend_title="Curvas reales",
    )


def plot_moment_curvature_bilinear_only(
    curve_results: list[dict[str, object]],
    path: str | Path,
    *,
    title: str = "Idealizacion bilineal momento-curvatura",
    subtitle: str = "Puntos notables de fluencia efectiva, ultimo y rigidez secante",
    xlabel: str = "Curvatura, phi [1/m]",
    ylabel: str = "Momento, M [kN-m]",
) -> Path:
    """Plot bilinearized moment-curvature curves with notable points in the legend."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(13.6, 6.8), dpi=180)
    fig.patch.set_facecolor("white")
    _style_axes(ax)
    ductility_handles: list[Any] = []
    legend_artists: list[Any] = []

    for index, result in enumerate(curve_results):
        curve_id = str(result["curve_id"])
        curve_name = str(result.get("name", curve_id))
        color = COLOR_CYCLE[index % len(COLOR_CYCLE)]
        bilinear_curve = result["bilinear_curve"]
        if not isinstance(bilinear_curve, list):
            continue

        bilinear_phi = [float(point["phi"]) for point in bilinear_curve]
        bilinear_moment = [float(point["moment"]) for point in bilinear_curve]
        point_parameters = _signed_point_parameters(result)

        ax.plot(
            bilinear_phi,
            bilinear_moment,
            color=color,
            linewidth=2.5,
            label=f"{curve_name} - bilineal",
        )
        if not point_parameters:
            continue

        cyclic_cut = _cyclic_cut_point_for_plot(result)
        ultimate_name = "Mu ciclico" if cyclic_cut is not None else "Mu"
        ultimate_phi_name = "phi_uc" if cyclic_cut is not None else "phi_u"
        ultimate_color = "#d79a2b" if cyclic_cut is not None else "#c43c2f"
        point_specs = [
            (
                "Fluencia efectiva",
                point_parameters["phi_y"],
                point_parameters["My"],
                "#2f7d4f",
                (
                    f"{curve_name} - My: {point_parameters['My']:.3g} [kN-m], "
                    f"phi_y: {point_parameters['phi_y']:.4g} [1/m]"
                ),
            ),
            (
                "Ultimo",
                point_parameters["phi_u"],
                point_parameters["Mu"],
                ultimate_color,
                (
                    f"{curve_name} - {ultimate_name}: {point_parameters['Mu']:.3g} [kN-m], "
                    f"{ultimate_phi_name}: {point_parameters['phi_u']:.4g} [1/m]"
                ),
            ),
            (
                "Rigidez secante",
                point_parameters["phi_60My"],
                point_parameters["M_60My"],
                "#7a4f9a",
                (
                    f"{curve_name} - 0.60My: {point_parameters['M_60My']:.3g} [kN-m], "
                    f"phi_0.60My: {point_parameters['phi_60My']:.4g} [1/m]"
                ),
            ),
        ]
        for _, phi_value, moment_value, marker_color, label in point_specs:
            if not _is_visible_moment_curvature_point(result, phi_value):
                continue
            ax.scatter(
                [phi_value],
                [moment_value],
                s=62,
                color=marker_color,
                edgecolor="white",
                linewidth=1.0,
                zorder=6,
                label=label,
            )

        ductility = abs(point_parameters["phi_u"]) / max(abs(point_parameters["phi_y"]), 1e-15)
        ductility_handles.append(
            Line2D(
                [0],
                [0],
                color=color,
                linewidth=2.5,
                label=f"{curve_name} | mu_phi = {ductility:.3g}",
            )
        )

    ax.axhline(0.0, color="#30343b", linewidth=0.8)
    ax.axvline(0.0, color="#30343b", linewidth=0.8)
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#222831", pad=16)
    if subtitle:
        ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=10, color="#5d636b", va="bottom")
    ax.set_xlabel(xlabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.set_ylabel(ylabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.margins(x=0.04, y=0.10)

    main_legend = _add_external_moment_curvature_legend(
        ax,
        loc="upper left",
        anchor_y=1.0,
        fontsize=7.8,
        title="Bilinealizacion y puntos notables",
        title_fontsize=8.8,
    )
    ax.add_artist(main_legend)
    legend_artists.append(main_legend)

    if ductility_handles:
        ductility_legend = _add_external_moment_curvature_legend(
            ax,
            handles=ductility_handles,
            loc="lower left",
            anchor_y=0.0,
            fontsize=8.2,
            title="Ductilidad por curvatura",
            title_fontsize=8.8,
        )
        legend_artists.append(ductility_legend)

    fig.text(
        0.99,
        0.015,
        "StructureLab_PBD_RC | Etapa 3",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#7b828a",
    )
    fig.tight_layout(rect=MOMENT_CURVATURE_EXTERNAL_LEGEND_RECT)
    fig.savefig(
        output_path,
        bbox_inches="tight",
        bbox_extra_artists=tuple(legend_artists),
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)
    return output_path


def plot_moment_curvature_real_vs_bilinear(
    curve_results: list[dict[str, object]],
    path: str | Path,
    *,
    title: str = "Comparacion momento-curvatura real vs bilineal",
    subtitle: str = "Curva real e idealizacion ASCE/FEMA en una misma grafica",
    xlabel: str = "Curvatura, phi [1/m]",
    ylabel: str = "Momento, M [kN-m]",
) -> Path:
    """Plot actual and bilinearized moment-curvature curves together."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(13.6, 6.8), dpi=180)
    fig.patch.set_facecolor("white")
    _style_axes(ax)
    curve_handles: list[Any] = []
    point_handles: list[Any] = []
    legend_artists: list[Any] = []

    for index, result in enumerate(curve_results):
        curve_id = str(result["curve_id"])
        curve_name = str(result.get("name", curve_id))
        color = COLOR_CYCLE[index % len(COLOR_CYCLE)]
        actual_curve = result["actual_curve"]
        bilinear_curve = result["bilinear_curve"]
        if not isinstance(actual_curve, list) or not isinstance(bilinear_curve, list):
            continue

        actual_phi = [float(point["phi"]) for point in actual_curve]
        actual_moment = [float(point["moment"]) for point in actual_curve]
        bilinear_phi = [float(point["phi"]) for point in bilinear_curve]
        bilinear_moment = [float(point["moment"]) for point in bilinear_curve]

        (actual_line,) = ax.plot(
            actual_phi,
            actual_moment,
            color=color,
            linewidth=2.2,
            label=f"{curve_name} - curva real",
        )
        (bilinear_line,) = ax.plot(
            bilinear_phi,
            bilinear_moment,
            color=color,
            linestyle="--",
            linewidth=2.4,
            label=f"{curve_name} - bilineal",
        )
        curve_handles.extend([actual_line, bilinear_line])

        point_parameters = _signed_point_parameters(result)
        if point_parameters:
            cyclic_cut = _cyclic_cut_point_for_plot(result)
            ultimate_name = "Mu ciclico" if cyclic_cut is not None else "Mu"
            ultimate_phi_name = "phi_uc" if cyclic_cut is not None else "phi_u"
            ultimate_color = "#d79a2b" if cyclic_cut is not None else "#c43c2f"
            point_specs = [
                (
                    point_parameters["phi_y"],
                    point_parameters["My"],
                    "#2f7d4f",
                    (
                        f"{curve_name} | My: {point_parameters['My']:.3g} [kN-m], "
                        f"phi_y: {point_parameters['phi_y']:.4g} [1/m]"
                    ),
                ),
                (
                    point_parameters["phi_u"],
                    point_parameters["Mu"],
                    ultimate_color,
                    (
                        f"{curve_name} | {ultimate_name}: {point_parameters['Mu']:.3g} [kN-m], "
                        f"{ultimate_phi_name}: {point_parameters['phi_u']:.4g} [1/m]"
                    ),
                ),
                (
                    point_parameters["phi_60My"],
                    point_parameters["M_60My"],
                    "#7a4f9a",
                    (
                        f"{curve_name} | 0.60My: {point_parameters['M_60My']:.3g} [kN-m], "
                        f"phi_0.60My: {point_parameters['phi_60My']:.4g} [1/m]"
                    ),
                ),
            ]
            for phi_value, moment_value, marker_color, label in point_specs:
                if not _is_visible_moment_curvature_point(result, phi_value):
                    continue
                ax.scatter(
                    [phi_value],
                    [moment_value],
                    s=58,
                    color=marker_color,
                    edgecolor="white",
                    linewidth=1.0,
                    zorder=6,
                )
                point_handles.append(
                    Line2D(
                        [0],
                        [0],
                        marker="o",
                        color="none",
                        markerfacecolor=marker_color,
                        markeredgecolor="white",
                        markeredgewidth=1.0,
                        markersize=8,
                        label=label,
                    )
                )

    ax.axhline(0.0, color="#30343b", linewidth=0.8)
    ax.axvline(0.0, color="#30343b", linewidth=0.8)
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#222831", pad=16)
    if subtitle:
        ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=10, color="#5d636b", va="bottom")
    ax.set_xlabel(xlabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.set_ylabel(ylabel, fontsize=11, fontweight="bold", color="#30343b", labelpad=10)
    ax.margins(x=0.04, y=0.10)

    curve_legend = _add_external_moment_curvature_legend(
        ax,
        handles=curve_handles,
        loc="upper left",
        anchor_y=1.0,
        fontsize=8.2,
        title="Curvas",
        title_fontsize=9,
    )
    ax.add_artist(curve_legend)
    legend_artists.append(curve_legend)

    if point_handles:
        point_legend = _add_external_moment_curvature_legend(
            ax,
            handles=point_handles,
            loc="lower left",
            anchor_y=0.0,
            fontsize=7.2,
            title="Puntos notables",
            title_fontsize=8.4,
        )
        legend_artists.append(point_legend)

    fig.text(
        0.99,
        0.015,
        "StructureLab_PBD_RC | Etapa 3",
        ha="right",
        va="bottom",
        fontsize=8,
        color="#7b828a",
    )
    fig.tight_layout(rect=MOMENT_CURVATURE_EXTERNAL_LEGEND_RECT)
    fig.savefig(
        output_path,
        bbox_inches="tight",
        bbox_extra_artists=tuple(legend_artists),
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)
    return output_path


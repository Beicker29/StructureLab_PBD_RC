"""In-memory presentation for precomputed section characterizations.

This layer serializes and plots values supplied by V2-020.  It never selects
ultimate/cut points and never invokes moment-curvature or idealization kernels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from types import MappingProxyType
from typing import Any, Mapping

from structurelab_pbd_rc.io.memory_artifacts import csv_rows_bytes, xlsx_rows_bytes
from structurelab_pbd_rc.services.section_characterization import (
    SectionModeResult,
    SectionSheetResult,
)


@dataclass(frozen=True)
class SectionPresentationArtifact:
    artifact_suffix: str
    artifact_type: str
    relative_name: str
    content: bytes
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_suffix or not self.artifact_type or not self.relative_name:
            raise ValueError("Presentation artifact identity must be non-empty.")
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("Presentation artifact content must be non-empty bytes.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def build_section_tables(
    sheet: SectionSheetResult,
    *,
    mode_name: str,
) -> tuple[SectionPresentationArtifact, ...]:
    """Serialize only the already-computed rows of one worksheet mode."""

    mode = _mode(sheet, mode_name)
    table_specs: list[tuple[str, str, tuple[Mapping[str, Any], ...]]] = [
        ("moment_curvature", "section_moment_curvature_table", mode.actual_curve_rows),
        ("bilinear_curves", "section_bilinear_curve_table", mode.bilinear_curve_rows),
        ("parameters", "section_idealization_parameters", mode.parameter_rows),
    ]
    if mode_name == "ciclica":
        table_specs.append(
            ("cut_points", "section_cut_points", mode.cut_point_rows)
        )
    artifacts: list[SectionPresentationArtifact] = []
    for suffix, artifact_type, source_rows in table_specs:
        rows = [dict(row) for row in source_rows]
        artifacts.extend(
            (
                SectionPresentationArtifact(
                    f"{mode_name}_{suffix}_csv",
                    artifact_type,
                    f"{suffix}.csv",
                    csv_rows_bytes(rows),
                    {
                        "format": "csv",
                        "row_count": len(rows),
                        "diagram_type": mode.diagram_type,
                    },
                ),
                SectionPresentationArtifact(
                    f"{mode_name}_{suffix}_xlsx",
                    artifact_type,
                    f"{suffix}.xlsx",
                    xlsx_rows_bytes(rows, sheet_name=suffix[:31]),
                    {
                        "format": "xlsx",
                        "row_count": len(rows),
                        "diagram_type": mode.diagram_type,
                    },
                ),
            )
        )
    return tuple(artifacts)


def _mode(sheet: SectionSheetResult, mode_name: str) -> SectionModeResult:
    if mode_name == "monotonica":
        return sheet.monotonica
    if mode_name == "ciclica":
        return sheet.ciclica
    raise ValueError(f"Unknown section presentation mode {mode_name!r}.")


def _groups(rows: tuple[Mapping[str, Any], ...]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["curve_id"]), []).append(row)
    return groups


def _figure_bytes(figure: Any) -> bytes:
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    stream = BytesIO()
    FigureCanvasAgg(figure)
    figure.savefig(
        stream,
        format="png",
        dpi=150,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "StructureLab_PBD_RC"},
    )
    figure.clear()
    return stream.getvalue()


def _section_figure(
    sheet: SectionSheetResult,
    mode: SectionModeResult,
    *,
    kind: str,
) -> bytes:
    from matplotlib.figure import Figure

    actual_groups = _groups(mode.actual_curve_rows)
    bilinear_groups = _groups(mode.bilinear_curve_rows)
    if not actual_groups or not bilinear_groups:
        raise ValueError("A section figure requires actual and bilinear curve rows.")
    figure = Figure(figsize=(10.5, 6.2), facecolor="white")
    axis = figure.subplots()
    axis.grid(True, color="#d7d9d4", linewidth=0.65, alpha=0.75)
    colors = ("#245b78", "#b34a38", "#4d7c46", "#775c9b")
    curve_ids = tuple(actual_groups)
    for index, curve_id in enumerate(curve_ids):
        color = colors[index % len(colors)]
        actual = actual_groups[curve_id]
        bilinear = bilinear_groups[curve_id]
        curve_name = str(actual[0]["curve_name"])
        if kind in {"actual", "comparison"}:
            axis.plot(
                [float(row["phi"]) for row in actual],
                [float(row["moment"]) for row in actual],
                color=color,
                linewidth=1.7,
                label=f"{curve_name} — curva",
            )
        if kind in {"bilinear", "comparison"}:
            axis.plot(
                [float(row["phi"]) for row in bilinear],
                [float(row["moment"]) for row in bilinear],
                color=color,
                linewidth=2.0,
                linestyle="--" if kind == "comparison" else "-",
                marker="o",
                markersize=3.5,
                label=f"{curve_name} — bilineal",
            )
    labels = {
        "actual": "Curvas momento–curvatura",
        "bilinear": "Idealizaciones bilineales",
        "comparison": "Curvas e idealizaciones bilineales",
    }
    axis.axhline(0.0, color="#30343b", linewidth=0.8)
    axis.axvline(0.0, color="#30343b", linewidth=0.8)
    axis.set_title(
        f"{sheet.sheet_name.strip()} — {labels[kind]} ({mode.diagram_type})",
        loc="left",
        fontsize=13,
        fontweight="bold",
    )
    axis.set_xlabel("Curvatura φ [1/m]")
    axis.set_ylabel("Momento M [kN-m]")
    axis.legend(loc="best", frameon=True, fontsize=8)
    figure.tight_layout()
    return _figure_bytes(figure)


def render_section_figures(
    sheet: SectionSheetResult,
    *,
    mode_name: str,
) -> tuple[SectionPresentationArtifact, ...]:
    """Render three views using only immutable result rows."""

    mode = _mode(sheet, mode_name)
    specs = (
        ("actual", "moment_curvature_real.png", "section_moment_curvature_figure"),
        ("bilinear", "bilinearization.png", "section_bilinearization_figure"),
        (
            "comparison",
            "moment_curvature_real_vs_bilinear.png",
            "section_bilinearization_figure",
        ),
    )
    return tuple(
        SectionPresentationArtifact(
            f"{mode_name}_{kind}_figure",
            artifact_type,
            filename,
            _section_figure(sheet, mode, kind=kind),
            {
                "format": "png",
                "source": "structured_section_result",
                "diagram_type": mode.diagram_type,
                "response_semantics": mode.response_semantics,
                "is_hysteretic": mode.is_hysteretic,
            },
        )
        for kind, filename, artifact_type in specs
    )


__all__ = [
    "SectionPresentationArtifact",
    "build_section_tables",
    "render_section_figures",
]

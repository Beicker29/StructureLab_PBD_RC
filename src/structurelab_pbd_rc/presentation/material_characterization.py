"""In-memory tables and figures for precomputed material evaluations.

This module is intentionally downstream of ``services.material_evaluation``.
It reads curve/result values and never calls a constitutive kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from types import MappingProxyType
from typing import Any, Mapping

from structurelab_pbd_rc.io.memory_artifacts import csv_rows_bytes, xlsx_rows_bytes
from structurelab_pbd_rc.services.material_evaluation import MaterialEvaluationResult


@dataclass(frozen=True)
class PresentationArtifact:
    """One rendered table or figure held entirely in memory."""

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


def build_material_tables(
    result: MaterialEvaluationResult,
) -> tuple[PresentationArtifact, ...]:
    """Serialize already-computed curves and idealization points."""

    model_id = result.instance.formulation.model_id
    rows = [dict(row) for row in result.curve]
    artifacts = [
        PresentationArtifact(
            "curve_csv",
            "material_response_table",
            "curve.csv",
            csv_rows_bytes(rows),
            {"format": "csv", "row_count": len(rows)},
        ),
        PresentationArtifact(
            "curve_xlsx",
            "material_response_table",
            "curve.xlsx",
            xlsx_rows_bytes(rows, sheet_name=model_id[:31]),
            {"format": "xlsx", "row_count": len(rows)},
        ),
    ]
    idealization = getattr(result, "idealization", None)
    if idealization is not None:
        bilinear = [dict(row) for row in idealization["bilinear_curve"]]
        artifacts.extend(
            (
                PresentationArtifact(
                    "idealization_csv",
                    "material_idealization_table",
                    "idealization.csv",
                    csv_rows_bytes(bilinear),
                    {"format": "csv", "row_count": len(bilinear)},
                ),
                PresentationArtifact(
                    "idealization_xlsx",
                    "material_idealization_table",
                    "idealization.xlsx",
                    xlsx_rows_bytes(bilinear, sheet_name="idealization"),
                    {"format": "xlsx", "row_count": len(bilinear)},
                ),
            )
        )
    return tuple(artifacts)


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


def _response_figure(result: MaterialEvaluationResult, *, title: str) -> bytes:
    from matplotlib.figure import Figure

    rows = [dict(row) for row in result.curve]
    if not rows:
        raise ValueError("A material response figure requires curve rows.")
    figure = Figure(figsize=(10.5, 6.2), facecolor="white")
    axis = figure.subplots()
    axis.grid(True, color="#d7d9d4", linewidth=0.65, alpha=0.75)

    formulation = result.instance.formulation
    if formulation.analysis_type == "cyclic":
        groups = {"Historia cíclica": rows}
    else:
        restraint_cases = {
            str(row["buckling_restraint_case"])
            for row in rows
            if row.get("buckling_restraint_case")
        }
        if restraint_cases:
            labels = {
                "bending": "Compresión — flexión",
                "pure_compression": "Compresión — carga axial",
                "reference_tension": "Tracción — referencia",
            }
            groups = {
                labels.get(case_name, case_name): [
                    row
                    for row in rows
                    if row.get("buckling_restraint_case") == case_name
                ]
                for case_name in sorted(restraint_cases)
            }
        else:
            groups = {
                state.capitalize(): [
                    row
                    for row in rows
                    if row.get("stress_state") in {state, "zero"}
                ]
                for state in ("compression", "tension")
                if any(row.get("stress_state") == state for row in rows)
            }
            if not groups:
                groups = {formulation.model_id: rows}

    for label, group in groups.items():
        ordered = group if formulation.analysis_type == "cyclic" else sorted(
            group, key=lambda row: float(row["strain"])
        )
        axis.plot(
            [float(row["strain"]) for row in ordered],
            [float(row["stress_mpa"]) for row in ordered],
            linewidth=1.9,
            label=label,
        )
    for point in result.notable_points:
        axis.scatter(
            [float(point["strain"])],
            [float(point["stress_mpa"])],
            s=32,
            color="#c43c2f",
            edgecolor="white",
            linewidth=0.7,
            zorder=5,
        )
    axis.axhline(0.0, color="#30343b", linewidth=0.8)
    axis.axvline(0.0, color="#30343b", linewidth=0.8)
    axis.set_title(title, loc="left", fontsize=14, fontweight="bold")
    axis.set_xlabel("Strain [mm/mm]")
    axis.set_ylabel("Stress [MPa]")
    axis.legend(loc="best", frameon=True, fontsize=8)
    figure.tight_layout()
    return _figure_bytes(figure)


def _idealization_figure(result: MaterialEvaluationResult, *, title: str) -> bytes:
    from matplotlib.figure import Figure

    idealization = getattr(result, "idealization", None)
    if idealization is None:
        raise ValueError("An idealization figure requires an idealization result.")
    rows = [dict(row) for row in result.curve]
    bilinear = [dict(row) for row in idealization["bilinear_curve"]]
    figure = Figure(figsize=(10.5, 6.2), facecolor="white")
    axis = figure.subplots()
    axis.grid(True, color="#d7d9d4", linewidth=0.65, alpha=0.75)
    axis.plot(
        [float(row["strain"]) for row in rows],
        [float(row["stress_mpa"]) for row in rows],
        linewidth=1.9,
        label="Respuesta calculada",
    )
    axis.plot(
        [float(row["strain"]) for row in bilinear],
        [float(row["stress_mpa"]) for row in bilinear],
        linewidth=2.0,
        linestyle="--",
        label="Idealización bilineal",
    )
    axis.axhline(0.0, color="#30343b", linewidth=0.8)
    axis.axvline(0.0, color="#30343b", linewidth=0.8)
    axis.set_title(f"{title} — idealización", loc="left", fontsize=14, fontweight="bold")
    axis.set_xlabel("Strain [mm/mm]")
    axis.set_ylabel("Stress [MPa]")
    axis.legend(loc="best", frameon=True, fontsize=8)
    figure.tight_layout()
    return _figure_bytes(figure)


def render_material_figures(
    result: MaterialEvaluationResult,
    *,
    title: str,
) -> tuple[PresentationArtifact, ...]:
    """Render figures from immutable result values, with no scientific calls."""

    artifacts = [
        PresentationArtifact(
            "response_figure",
            "material_response_figure",
            "response.png",
            _response_figure(result, title=title),
            {"format": "png", "source": "structured_material_result"},
        )
    ]
    if getattr(result, "idealization", None) is not None:
        artifacts.append(
            PresentationArtifact(
                "idealization_figure",
                "material_idealization_figure",
                "idealization.png",
                _idealization_figure(result, title=title),
                {"format": "png", "source": "structured_material_result"},
            )
        )
    return tuple(artifacts)

"""Pure in-memory characterization of imported moment-curvature curves.

This V2-020 service adapts structured worksheet rows to the unchanged V1
moment-curvature kernels.  It deliberately performs no workbook access,
filesystem writes, plotting, reporting, publication, or workflow registration.

The legacy output name ``ciclica`` is preserved as data vocabulary only.  Its
contents are a truncated or reused monotonic backbone and are explicitly not a
hysteretic response.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.mechanics.sections.moment_curvature import (
    BilinearizationSettings,
    MomentCurvaturePoint,
    bilinearize_moment_curvature,
    truncate_moment_curvature_curve_at_point,
)


NATIVE_UNITS = {"curvature": "1/m", "moment": "kN-m"}
SUPPORTED_METHOD = "asce_fema_energy_equivalent_m_phi"
LEGACY_CYCLIC_OUTPUT_NAME = "ciclica"
LEGACY_CYCLIC_RESPONSE_SEMANTICS = "truncated_or_reused_monotonic_backbone"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return deepcopy(value)


def _mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be an object.")
    return value


def _required(mapping: Mapping[str, Any], keys: Sequence[str], *, context: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ConfigError(f"{context} is missing required keys: {', '.join(missing)}")


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _column_index(column: str) -> int:
    index = 0
    for character in column.upper():
        index = index * 26 + ord(character) - 64
    return index


def _column_from_index(index: int) -> str:
    letters = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _safe_sheet_label(sheet_name: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if character in invalid else character for character in sheet_name).strip()
    return cleaned.rstrip(".") or "sheet"


@dataclass(frozen=True)
class SectionWorksheetInput:
    """One already-read worksheet supplied as structured row mappings."""

    sheet_name: str
    rows: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if not self.sheet_name:
            raise ConfigError("worksheet sheet_name must be non-empty.")
        frozen_rows = tuple(_freeze(_mapping(row, context="worksheet row")) for row in self.rows)
        object.__setattr__(self, "rows", frozen_rows)

    @classmethod
    def from_rows(
        cls, sheet_name: str, rows: Sequence[Mapping[str, Any]]
    ) -> "SectionWorksheetInput":
        return cls(sheet_name=sheet_name, rows=tuple(rows))


@dataclass(frozen=True)
class SectionCharacterizationInput:
    """Resolved Stage 03 settings plus in-memory worksheet contents."""

    config: Mapping[str, Any]
    worksheets: tuple[SectionWorksheetInput, ...]
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        config = _mapping(self.config, context="section characterization config")
        _validate_config(config)
        if not self.worksheets:
            raise ConfigError("section characterization requires at least one worksheet.")
        names = [worksheet.sheet_name for worksheet in self.worksheets]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ConfigError(f"Duplicate worksheet names are not allowed: {duplicates}")
        object.__setattr__(self, "config", _freeze(config))
        object.__setattr__(self, "worksheets", tuple(self.worksheets))
        object.__setattr__(
            self,
            "provenance",
            _freeze(_mapping(self.provenance, context="section characterization provenance")),
        )

    @classmethod
    def from_resolved_inputs(
        cls,
        config: Mapping[str, Any],
        *,
        worksheets: Sequence[SectionWorksheetInput],
        provenance: Mapping[str, Any],
    ) -> "SectionCharacterizationInput":
        """Build a request without resolving a path or reading a workbook."""

        return cls(
            config=config,
            worksheets=tuple(worksheets),
            provenance=provenance,
        )


@dataclass(frozen=True)
class CyclicCutSelection:
    """Traceable interpretation of a legacy ``ciclica`` cut request."""

    mode: str
    point: Mapping[str, float] | None
    reason: str

    def __post_init__(self) -> None:
        if self.mode not in {"configured", "auto", "absent", "disabled"}:
            raise ConfigError(f"Unsupported cut selection mode {self.mode!r}.")
        if self.mode == "configured" and self.point is None:
            raise ConfigError("A configured cut selection requires a point.")
        if self.mode != "configured" and self.point is not None:
            raise ConfigError("Only a configured cut selection may carry a point.")
        if self.point is not None:
            object.__setattr__(self, "point", _freeze(self.point))


@dataclass(frozen=True)
class SectionBranchResult:
    """Detected branch and its monotonic/legacy-cyclic characterizations."""

    curve: Mapping[str, Any]
    source_points: tuple[MomentCurvaturePoint, ...]
    monotonic: Mapping[str, Any]
    ciclica: Mapping[str, Any]
    cut_selection: CyclicCutSelection
    ciclica_reuses_monotonic: bool
    warnings: tuple[str, ...]
    ciclica_output_name: str = LEGACY_CYCLIC_OUTPUT_NAME
    ciclica_response_semantics: str = LEGACY_CYCLIC_RESPONSE_SEMANTICS
    ciclica_is_hysteretic: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "curve", _freeze(self.curve))
        object.__setattr__(self, "source_points", tuple(self.source_points))
        object.__setattr__(self, "monotonic", _freeze(self.monotonic))
        if self.ciclica_reuses_monotonic:
            object.__setattr__(self, "ciclica", self.monotonic)
        else:
            object.__setattr__(self, "ciclica", _freeze(self.ciclica))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True)
class SectionModeResult:
    """Structured scientific tables corresponding to one historical mode."""

    diagram_type: str
    actual_curve_rows: tuple[Mapping[str, Any], ...]
    bilinear_curve_rows: tuple[Mapping[str, Any], ...]
    parameter_rows: tuple[Mapping[str, Any], ...]
    cut_point_rows: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    response_semantics: str
    is_hysteretic: bool

    def __post_init__(self) -> None:
        for field_name in (
            "actual_curve_rows",
            "bilinear_curve_rows",
            "parameter_rows",
            "cut_point_rows",
        ):
            rows = getattr(self, field_name)
            object.__setattr__(self, field_name, tuple(_freeze(row) for row in rows))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True)
class SectionSheetResult:
    sheet_name: str
    branches: tuple[SectionBranchResult, ...]
    monotonica: SectionModeResult
    ciclica: SectionModeResult
    status: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SectionCharacterizationResult:
    """Complete in-memory output of V2-020."""

    status: str
    method: str
    units: Mapping[str, str]
    sheets: tuple[SectionSheetResult, ...]
    warnings: tuple[str, ...]
    provenance: Mapping[str, Any]
    service_id: str = "section_characterization"
    implementation_version: str = "v2-020"

    def __post_init__(self) -> None:
        object.__setattr__(self, "units", _freeze(self.units))
        object.__setattr__(self, "sheets", tuple(self.sheets))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)

    @property
    def curve_count(self) -> int:
        return sum(len(sheet.branches) for sheet in self.sheets)


def _validate_config(config: Mapping[str, Any]) -> None:
    _required(config, ("units", "curve_detection", "bilinearization"), context="config")
    units = _mapping(config["units"], context="units")
    if dict(units) != NATIVE_UNITS:
        raise ConfigError(
            f"Section service accepts native units exactly {NATIVE_UNITS!r}; "
            "perform V2 unit/sign conversion at the module boundary."
        )

    detection = _mapping(config["curve_detection"], context="curve_detection")
    _required(
        detection,
        (
            "title_row",
            "header_row",
            "first_data_row",
            "curvature_header_contains",
            "moment_header_contains",
        ),
        context="curve_detection",
    )
    bilinearization = _mapping(config["bilinearization"], context="bilinearization")
    _required(
        bilinearization,
        (
            "method",
            "stiffness_fraction",
            "tolerance",
            "search_points",
            "my_lower_ratio",
            "my_upper_ratio",
            "ultimate",
        ),
        context="bilinearization",
    )
    if bilinearization["method"] != SUPPORTED_METHOD:
        raise ConfigError(f"Unsupported bilinearization method {bilinearization['method']!r}.")
    ultimate = _mapping(bilinearization["ultimate"], context="bilinearization.ultimate")
    _required(ultimate, ("mode",), context="bilinearization.ultimate")
    if "cyclic_diagram" in config:
        cyclic = _mapping(config["cyclic_diagram"], context="cyclic_diagram")
        _required(cyclic, ("enabled", "cut_points_by_sheet"), context="cyclic_diagram")


def _row_by_number(rows: Sequence[Mapping[str, Any]], row_number: int) -> Mapping[str, Any]:
    for row in rows:
        if int(row.get("__row_number__", 0)) == row_number:
            return row
    return {}


def _curve_sign_from_data(
    rows: Sequence[Mapping[str, Any]], moment_column: str, first_data_row: int
) -> str:
    values: list[float] = []
    for row in rows:
        if int(row.get("__row_number__", 0)) < first_data_row:
            continue
        moment = _as_float(row.get(moment_column))
        if moment is not None and abs(moment) > 1e-12:
            values.append(moment)
        if len(values) >= 5:
            break
    negative_count = sum(value < 0.0 for value in values)
    return "negative" if negative_count > len(values) / 2 else "positive"


def _curve_name(sheet_name: str, sign: str, occurrence: int) -> str:
    branch_suffix = "" if sign == "positive" else "-INV"
    occurrence_suffix = "" if occurrence == 1 else f" ({occurrence})"
    return f"{sheet_name.strip()}{branch_suffix}{occurrence_suffix}"


def _detect_curves(
    rows: Sequence[Mapping[str, Any]], sheet_name: str, config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    detection = _mapping(config["curve_detection"], context="curve_detection")
    header = _row_by_number(rows, int(detection["header_row"]))
    first_data_row = int(detection["first_data_row"])
    curvature_pattern = str(detection["curvature_header_contains"]).lower()
    moment_pattern = str(detection["moment_header_contains"]).lower()
    curves: list[dict[str, Any]] = []
    sign_counts = {"positive": 0, "negative": 0}

    sortable = sorted(
        header.items(),
        key=lambda item: _column_index(item[0]) if not item[0].startswith("__") else 0,
    )
    for column, value in sortable:
        if column.startswith("__") or value is None:
            continue
        if curvature_pattern not in str(value).lower():
            continue
        moment_column = _column_from_index(_column_index(column) + 1)
        moment_header = header.get(moment_column)
        if moment_header is None or moment_pattern not in str(moment_header).lower():
            continue
        sign = _curve_sign_from_data(rows, moment_column, first_data_row)
        sign_counts[sign] += 1
        suffix = "" if sign_counts[sign] == 1 else f"_{sign_counts[sign]}"
        curves.append(
            {
                "id": f"{sign}_bending{suffix}",
                "name": _curve_name(sheet_name, sign, sign_counts[sign]),
                "sign": sign,
                "curvature_column": column,
                "moment_column": moment_column,
                "first_data_row": first_data_row,
            }
        )
    if not curves:
        raise ConfigError(f"No moment-curvature column pairs were detected in sheet {sheet_name!r}.")
    return curves


def _extract_points(
    rows: Sequence[Mapping[str, Any]], curve: Mapping[str, Any]
) -> list[MomentCurvaturePoint]:
    points: list[MomentCurvaturePoint] = []
    first_data_row = int(curve["first_data_row"])
    curvature_column = str(curve["curvature_column"]).upper()
    moment_column = str(curve["moment_column"]).upper()
    for row in rows:
        if int(row.get("__row_number__", 0)) < first_data_row:
            continue
        phi = _as_float(row.get(curvature_column))
        moment = _as_float(row.get(moment_column))
        if phi is not None and moment is not None:
            points.append(MomentCurvaturePoint(phi=phi, moment=moment))
    if len(points) < 3:
        raise ConfigError(f"Curve {curve['id']} must contain at least three numeric points.")
    return points


def _settings(config: Mapping[str, Any]) -> BilinearizationSettings:
    values = _mapping(config["bilinearization"], context="bilinearization")
    return BilinearizationSettings(
        stiffness_fraction=float(values["stiffness_fraction"]),
        tolerance=float(values["tolerance"]),
        search_points=int(values["search_points"]),
        my_lower_ratio=float(values["my_lower_ratio"]),
        my_upper_ratio=float(values["my_upper_ratio"]),
    )


def _configured_phi_u(
    points: Sequence[MomentCurvaturePoint], config: Mapping[str, Any]
) -> float | None:
    bilinearization = _mapping(config["bilinearization"], context="bilinearization")
    ultimate = _mapping(bilinearization["ultimate"], context="bilinearization.ultimate")
    mode = ultimate["mode"]
    if mode == "user_defined_phi_u":
        return float(ultimate["phi_u"])
    if mode == "final_valid_point":
        return max(abs(point.phi) for point in points)
    if mode == "first_post_peak_strength_drop":
        return None
    raise ConfigError(f"Unsupported ultimate mode {mode!r}.")


def _sign(curve: Mapping[str, Any]) -> float:
    return -1.0 if curve["sign"] == "negative" else 1.0


def _cut_selection(
    config: Mapping[str, Any], sheet_name: str, curve: Mapping[str, Any]
) -> CyclicCutSelection:
    cyclic = config.get("cyclic_diagram")
    if not isinstance(cyclic, Mapping) or not bool(cyclic.get("enabled", False)):
        return CyclicCutSelection(
            mode="disabled",
            point=None,
            reason="cyclic_diagram is absent or disabled; reuse monotonic characterization",
        )
    by_sheet = cyclic.get("cut_points_by_sheet")
    if not isinstance(by_sheet, Mapping):
        return CyclicCutSelection(
            mode="absent", point=None, reason="cut_points_by_sheet is not available"
        )
    sheet_cuts = by_sheet.get(sheet_name)
    if sheet_cuts is None:
        sheet_cuts = by_sheet.get(sheet_name.strip())
    if sheet_cuts is None:
        sheet_cuts = by_sheet.get(_safe_sheet_label(sheet_name))
    if not isinstance(sheet_cuts, Mapping):
        return CyclicCutSelection(
            mode="absent", point=None, reason="no cut is configured for this worksheet"
        )
    curve_id = str(curve["id"])
    branch_key = "negative_bending" if curve["sign"] == "negative" else "positive_bending"
    raw = sheet_cuts.get(curve_id, sheet_cuts.get(branch_key))
    if not isinstance(raw, Mapping):
        return CyclicCutSelection(
            mode="absent", point=None, reason="no cut is configured for this branch"
        )
    phi = _as_float(raw.get("phi"))
    moment = _as_float(raw.get("moment"))
    if phi is None or moment is None or abs(phi) <= 1e-15:
        return CyclicCutSelection(
            mode="auto",
            point=None,
            reason="automatic cut reuses the monotonic characterization",
        )
    branch_sign = _sign(curve)
    return CyclicCutSelection(
        mode="configured",
        point={"phi": branch_sign * abs(phi), "moment": branch_sign * abs(moment)},
        reason="explicit cut supplied for this worksheet branch",
    )


def _curve_rows(
    curve: Mapping[str, Any], result: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    branch_sign = _sign(curve)
    actual: list[dict[str, Any]] = []
    for index, point in enumerate(result["actual_curve"]):
        phi = float(point["phi"])
        moment = float(point["moment"])
        actual.append(
            {
                "curve_id": curve["id"],
                "curve_name": curve["name"],
                "point_index": index,
                "phi": branch_sign * phi,
                "moment": branch_sign * moment,
                "phi_abs": phi,
                "moment_abs": moment,
            }
        )
    bilinear: list[dict[str, Any]] = []
    for index, point in enumerate(result["bilinear_curve"]):
        phi = float(point["phi"])
        moment = float(point["moment"])
        bilinear.append(
            {
                "curve_id": curve["id"],
                "curve_name": curve["name"],
                "point_index": index,
                "point": point["point"],
                "phi": branch_sign * phi,
                "moment": branch_sign * moment,
                "phi_abs": phi,
                "moment_abs": moment,
            }
        )
    return actual, bilinear


def _parameter_row(curve: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    parameters = result["parameters"]
    peak = result["peak"]
    area = result["area"]
    branch_sign = _sign(curve)
    return {
        "curve_id": curve["id"],
        "curve_name": curve["name"],
        "Ke": parameters["Ke"],
        "My": parameters["My"],
        "phi_y": parameters["phi_y"],
        "Kp": parameters["Kp"],
        "alpha": parameters["alpha"],
        "Mu": parameters["Mu"],
        "phi_u": parameters["phi_u"],
        "signed_My": branch_sign * float(parameters["My"]),
        "signed_phi_y": branch_sign * float(parameters["phi_y"]),
        "signed_Mu": branch_sign * float(parameters["Mu"]),
        "signed_phi_u": branch_sign * float(parameters["phi_u"]),
        "M_60My": parameters["M_60My"],
        "phi_60My": parameters["phi_60My"],
        "M_peak": peak["moment"],
        "phi_peak": peak["phi"],
        "A_real": area["A_real"],
        "A_bilinear": area["A_bilinear"],
        "relative_error": parameters["relative_error"],
        "absolute_relative_error": parameters["absolute_relative_error"],
        "ductility_phi": parameters["ductility_phi"],
        "status": result["status"],
    }


def _cyclic_parameter_row(
    curve: Mapping[str, Any], result: Mapping[str, Any], selection: CyclicCutSelection
) -> dict[str, Any]:
    row = _parameter_row(curve, result)
    if selection.point is not None:
        phi = float(selection.point["phi"])
        moment = float(selection.point["moment"])
        row.update(
            {
                "cyclic_cut_phi": phi,
                "cyclic_cut_moment": moment,
                "cyclic_cut_phi_abs": abs(phi),
                "cyclic_cut_moment_abs": abs(moment),
                "phi_u_ciclico": phi,
                "Mu_ciclico": moment,
            }
        )
    else:
        row.update(
            {
                "cyclic_cut_phi": "",
                "cyclic_cut_moment": "",
                "cyclic_cut_phi_abs": "",
                "cyclic_cut_moment_abs": "",
                "phi_u_ciclico": "",
                "Mu_ciclico": "",
            }
        )
    return row


def _cut_row(curve: Mapping[str, Any], selection: CyclicCutSelection) -> dict[str, Any]:
    if selection.point is not None:
        phi = float(selection.point["phi"])
        moment = float(selection.point["moment"])
        return {
            "curve_id": curve["id"],
            "curve_name": curve["name"],
            "mode": "configured",
            "phi": phi,
            "moment": moment,
            "phi_abs": abs(phi),
            "moment_abs": abs(moment),
            "phi_u_ciclico": phi,
            "Mu_ciclico": moment,
        }
    # V1 serialized all reuse cases as ``auto``.  The structured selection
    # retains whether the actual reason was auto, absent, or disabled.
    return {
        "curve_id": curve["id"],
        "curve_name": curve["name"],
        "mode": "auto",
        "phi": "",
        "moment": "",
        "phi_abs": "",
        "moment_abs": "",
        "phi_u_ciclico": "",
        "Mu_ciclico": "",
    }


class SectionCharacterizationService:
    """Evaluate imported M-phi worksheets entirely in memory."""

    def evaluate(self, request: SectionCharacterizationInput) -> SectionCharacterizationResult:
        config = request.config
        settings = _settings(config)
        ultimate = _mapping(
            _mapping(config["bilinearization"], context="bilinearization")["ultimate"],
            context="bilinearization.ultimate",
        )
        strength_ratio = float(ultimate.get("post_peak_strength_ratio", 0.80))
        sheets: list[SectionSheetResult] = []
        all_warnings: list[str] = []

        for worksheet in request.worksheets:
            curves = _detect_curves(worksheet.rows, worksheet.sheet_name, config)
            branches: list[SectionBranchResult] = []
            monotonic_actual: list[Mapping[str, Any]] = []
            monotonic_bilinear: list[Mapping[str, Any]] = []
            monotonic_parameters: list[Mapping[str, Any]] = []
            cyclic_actual: list[Mapping[str, Any]] = []
            cyclic_bilinear: list[Mapping[str, Any]] = []
            cyclic_parameters: list[Mapping[str, Any]] = []
            cut_rows: list[Mapping[str, Any]] = []
            sheet_warnings: list[str] = []

            for curve in curves:
                points = _extract_points(worksheet.rows, curve)
                monotonic = bilinearize_moment_curvature(
                    points,
                    phi_u=_configured_phi_u(points, config),
                    post_peak_strength_ratio=strength_ratio,
                    settings=settings,
                )
                branch_warnings: list[str] = []
                if monotonic["status"] != "converged":
                    warning = (
                        f"{worksheet.sheet_name}/{curve['id']}: bilinearization did not reach "
                        "tolerance; best error = "
                        f"{monotonic['parameters']['absolute_relative_error']:.4g}."
                    )
                    branch_warnings.append(warning)
                    sheet_warnings.append(warning)
                    all_warnings.append(warning)

                selection = _cut_selection(config, worksheet.sheet_name, curve)
                if selection.point is None:
                    cyclic = monotonic
                    reused = True
                else:
                    cyclic_points = truncate_moment_curvature_curve_at_point(
                        points,
                        phi_u=abs(float(selection.point["phi"])),
                        moment_u=abs(float(selection.point["moment"])),
                    )
                    cyclic = bilinearize_moment_curvature(
                        cyclic_points,
                        phi_u=abs(float(selection.point["phi"])),
                        post_peak_strength_ratio=strength_ratio,
                        settings=settings,
                    )
                    reused = False
                    if cyclic["status"] != "converged":
                        warning = (
                            f"{worksheet.sheet_name}/{curve['id']}/ciclica: bilinearization did not "
                            "reach tolerance; best error = "
                            f"{cyclic['parameters']['absolute_relative_error']:.4g}."
                        )
                        branch_warnings.append(warning)
                        sheet_warnings.append(warning)
                        all_warnings.append(warning)

                mono_actual_rows, mono_bilinear_rows = _curve_rows(curve, monotonic)
                cyc_actual_rows, cyc_bilinear_rows = _curve_rows(curve, cyclic)
                monotonic_actual.extend(mono_actual_rows)
                monotonic_bilinear.extend(mono_bilinear_rows)
                monotonic_parameters.append(_parameter_row(curve, monotonic))
                cyclic_actual.extend(cyc_actual_rows)
                cyclic_bilinear.extend(cyc_bilinear_rows)
                cyclic_parameters.append(_cyclic_parameter_row(curve, cyclic, selection))
                cut_rows.append(_cut_row(curve, selection))
                branches.append(
                    SectionBranchResult(
                        curve=curve,
                        source_points=tuple(points),
                        monotonic=monotonic,
                        ciclica=cyclic,
                        cut_selection=selection,
                        ciclica_reuses_monotonic=reused,
                        warnings=tuple(branch_warnings),
                    )
                )

            monotonica = SectionModeResult(
                diagram_type="monotonica",
                actual_curve_rows=tuple(monotonic_actual),
                bilinear_curve_rows=tuple(monotonic_bilinear),
                parameter_rows=tuple(monotonic_parameters),
                cut_point_rows=(),
                warnings=tuple(sheet_warnings),
                response_semantics="monotonic_backbone",
                is_hysteretic=False,
            )
            ciclica = SectionModeResult(
                diagram_type=LEGACY_CYCLIC_OUTPUT_NAME,
                actual_curve_rows=tuple(cyclic_actual),
                bilinear_curve_rows=tuple(cyclic_bilinear),
                parameter_rows=tuple(cyclic_parameters),
                cut_point_rows=tuple(cut_rows),
                warnings=tuple(sheet_warnings),
                response_semantics=LEGACY_CYCLIC_RESPONSE_SEMANTICS,
                is_hysteretic=False,
            )
            sheets.append(
                SectionSheetResult(
                    sheet_name=worksheet.sheet_name,
                    branches=tuple(branches),
                    monotonica=monotonica,
                    ciclica=ciclica,
                    status="completed",
                    warnings=tuple(sheet_warnings),
                )
            )

        provenance = {
            "inputs": request.provenance,
            "scientific_kernel": "mechanics.sections.moment_curvature",
            "idealization_kernel": "mechanics.idealization.energy_equivalent",
            "implementation_version": "v2-020",
        }
        return SectionCharacterizationResult(
            status="completed",
            method=SUPPORTED_METHOD,
            units=NATIVE_UNITS,
            sheets=tuple(sheets),
            warnings=tuple(all_warnings),
            provenance=provenance,
        )


def characterize_sections(
    request: SectionCharacterizationInput,
) -> SectionCharacterizationResult:
    """Functional entry point for the pure in-memory service."""

    return SectionCharacterizationService().evaluate(request)


__all__ = [
    "CyclicCutSelection",
    "LEGACY_CYCLIC_OUTPUT_NAME",
    "LEGACY_CYCLIC_RESPONSE_SEMANTICS",
    "NATIVE_UNITS",
    "SectionBranchResult",
    "SectionCharacterizationInput",
    "SectionCharacterizationResult",
    "SectionCharacterizationService",
    "SectionModeResult",
    "SectionSheetResult",
    "SectionWorksheetInput",
    "characterize_sections",
]

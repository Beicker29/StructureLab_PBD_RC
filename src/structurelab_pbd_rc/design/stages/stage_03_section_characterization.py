"""Flujo de Etapa 3: caracterizacion de seccion por diagrama M-phi."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.design.stages._base import prepare_stage_from_config
from structurelab_pbd_rc.io.paths import stage_results_json_path
from structurelab_pbd_rc.io.read_xlsx import list_xlsx_sheets, read_xlsx_rows
from structurelab_pbd_rc.io.write_results import write_csv_rows, write_json_result, write_yaml_result
from structurelab_pbd_rc.mechanics.sections.moment_curvature import (
    BilinearizationSettings,
    MomentCurvaturePoint,
    bilinearize_moment_curvature,
    truncate_moment_curvature_curve_at_point,
)
from structurelab_pbd_rc.reports.plots import (
    plot_moment_curvature_bilinear_only,
    plot_moment_curvature_real_curves,
    plot_moment_curvature_real_vs_bilinear,
)

DEFAULT_CONFIG_PATH = Path("configs/stage_03/section_characterization.yaml")

REQUIRED_TOP_LEVEL_KEYS = ("units", "source", "curve_detection", "bilinearization")


def validate_stage_03_config(config: dict[str, Any]) -> None:
    """Validate the editable structure required by Etapa 3."""

    require_keys(config, REQUIRED_TOP_LEVEL_KEYS, context="stage_03 configuration")
    require_keys(config["units"], ["curvature", "moment"], context="units")
    if config["units"]["curvature"] != "1/m":
        raise ValueError("Unsupported curvature unit: expected 1/m")
    if config["units"]["moment"] != "kN-m":
        raise ValueError("Unsupported moment unit: expected kN-m")

    require_keys(config["source"], ["workbook", "sheets"], context="source")
    require_keys(
        config["curve_detection"],
        [
            "title_row",
            "header_row",
            "first_data_row",
            "curvature_header_contains",
            "moment_header_contains",
        ],
        context="curve_detection",
    )

    require_keys(
        config["bilinearization"],
        ["method", "stiffness_fraction", "tolerance", "search_points", "my_lower_ratio", "my_upper_ratio", "ultimate"],
        context="bilinearization",
    )
    if config["bilinearization"]["method"] != "asce_fema_energy_equivalent_m_phi":
        raise ValueError("Unsupported bilinearization method.")
    require_keys(config["bilinearization"]["ultimate"], ["mode"], context="bilinearization.ultimate")
    if "cyclic_diagram" in config:
        require_keys(config["cyclic_diagram"], ["enabled", "cut_points_by_sheet"], context="cyclic_diagram")


def _as_float(value: Any) -> float | None:
    """Return value as float when possible."""

    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _curve_sign(curve_config: dict[str, Any]) -> float:
    """Return numeric sign for a configured branch."""

    return -1.0 if curve_config["sign"] == "negative" else 1.0


def _column_index(column: str) -> int:
    """Return one-based column index from Excel letters."""

    index = 0
    for character in column.upper():
        index = index * 26 + ord(character) - 64
    return index


def _column_from_index(index: int) -> str:
    """Return Excel column letters from a one-based index."""

    letters = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _safe_sheet_folder_name(sheet_name: str) -> str:
    """Return a filesystem-safe folder name preserving the visible sheet name."""

    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if character in invalid else character for character in sheet_name).strip()
    cleaned = cleaned.rstrip(".")
    return cleaned or "sheet"


def _reset_stage_output_root(stage_root: Path, stage_id: str) -> dict[str, Path]:
    """Delete and recreate the stage output root for a fresh execution."""

    if stage_root.exists():
        resolved = stage_root.resolve()
        if resolved.name != stage_id:
            raise ValueError(f"Refusing to reset unexpected stage output directory: {resolved}")
        shutil.rmtree(resolved)
    data_dir = stage_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return {"root": stage_root, "data": data_dir}


def _selected_sheet_names(config: dict[str, Any], workbook_path: Path) -> list[str]:
    """Return workbook sheets requested by the stage config."""

    available = list_xlsx_sheets(workbook_path)
    requested = config["source"]["sheets"]
    if requested == "all":
        return available
    if isinstance(requested, str):
        requested_names = [requested]
    else:
        requested_names = [str(sheet) for sheet in requested]
    missing = [sheet for sheet in requested_names if sheet not in available]
    if missing:
        raise ValueError(f"Configured sheets not found in {workbook_path}: {missing}. Available sheets: {available}")
    return requested_names


def _row_by_number(rows: list[dict[str, Any]], row_number: int) -> dict[str, Any]:
    """Find a row by Excel row number."""

    for row in rows:
        if int(row.get("__row_number__", 0)) == row_number:
            return row
    return {}


def _curve_name_from_sheet_name(sheet_name: str, sign: str, occurrence: int) -> str:
    """Return a stable visible curve name from the workbook sheet name."""

    base_name = sheet_name.strip()
    branch_suffix = "" if sign == "positive" else "-INV"
    occurrence_suffix = "" if occurrence == 1 else f" ({occurrence})"
    return f"{base_name}{branch_suffix}{occurrence_suffix}"


def _curve_sign_from_data(rows: list[dict[str, Any]], moment_column: str, first_data_row: int) -> str:
    """Infer branch sign from the first nonzero moments."""

    values: list[float] = []
    for row in rows:
        if int(row.get("__row_number__", 0)) < first_data_row:
            continue
        moment = _as_float(row.get(moment_column))
        if moment is not None and abs(moment) > 1e-12:
            values.append(moment)
        if len(values) >= 5:
            break
    negative_count = sum(1 for value in values if value < 0.0)
    return "negative" if negative_count > len(values) / 2 else "positive"


def _detect_sheet_curves(rows: list[dict[str, Any]], sheet_name: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect moment-curvature column pairs from configured header text."""

    detection = config["curve_detection"]
    header_row = _row_by_number(rows, int(detection["header_row"]))
    first_data_row = int(detection["first_data_row"])
    curvature_pattern = str(detection["curvature_header_contains"]).lower()
    moment_pattern = str(detection["moment_header_contains"]).lower()
    curves: list[dict[str, Any]] = []
    sign_counts = {"positive": 0, "negative": 0}

    for column, value in sorted(header_row.items(), key=lambda item: _column_index(item[0]) if not item[0].startswith("__") else 0):
        if column.startswith("__") or value is None:
            continue
        if curvature_pattern not in str(value).lower():
            continue
        moment_column = _column_from_index(_column_index(column) + 1)
        moment_header = header_row.get(moment_column)
        if moment_header is None or moment_pattern not in str(moment_header).lower():
            continue
        sign = _curve_sign_from_data(rows, moment_column, first_data_row)
        sign_counts[sign] += 1
        suffix = "" if sign_counts[sign] == 1 else f"_{sign_counts[sign]}"
        curve_id = f"{sign}_bending{suffix}"
        curves.append(
            {
                "id": curve_id,
                "name": _curve_name_from_sheet_name(sheet_name, sign, sign_counts[sign]),
                "sign": sign,
                "curvature_column": column,
                "moment_column": moment_column,
                "first_data_row": first_data_row,
            }
        )

    if not curves:
        raise ValueError(f"No moment-curvature column pairs were detected in sheet '{sheet_name}'.")
    return curves


def _sheet_output_dirs(stage_root: Path, sheet_name: str) -> dict[str, Path]:
    """Create output directories for one Excel sheet."""

    root = stage_root / _safe_sheet_folder_name(sheet_name)
    monotonic_root = root / "monotonica"
    cyclic_root = root / "ciclica"
    dirs = {
        "root": root,
        "monotonica": monotonic_root,
        "monotonica_data": monotonic_root / "data",
        "monotonica_figures": monotonic_root / "figures",
        "monotonica_reports": monotonic_root / "reports",
        "ciclica": cyclic_root,
        "ciclica_data": cyclic_root / "data",
        "ciclica_figures": cyclic_root / "figures",
        "ciclica_reports": cyclic_root / "reports",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _extract_curve_points(rows: list[dict[str, Any]], curve_config: dict[str, Any]) -> list[MomentCurvaturePoint]:
    """Extract a moment-curvature curve from XLSX rows."""

    curvature_column = str(curve_config["curvature_column"]).upper()
    moment_column = str(curve_config["moment_column"]).upper()
    first_data_row = int(curve_config["first_data_row"])
    points: list[MomentCurvaturePoint] = []

    for row in rows:
        if int(row.get("__row_number__", 0)) < first_data_row:
            continue
        phi = _as_float(row.get(curvature_column))
        moment = _as_float(row.get(moment_column))
        if phi is None or moment is None:
            continue
        points.append(MomentCurvaturePoint(phi=phi, moment=moment))

    if len(points) < 3:
        raise ValueError(f"Curve {curve_config['id']} must contain at least three numeric points.")
    return points


def _settings_from_config(config: dict[str, Any]) -> BilinearizationSettings:
    """Build bilinearization settings from YAML config."""

    bilinearization = config["bilinearization"]
    return BilinearizationSettings(
        stiffness_fraction=float(bilinearization["stiffness_fraction"]),
        tolerance=float(bilinearization["tolerance"]),
        search_points=int(bilinearization["search_points"]),
        my_lower_ratio=float(bilinearization["my_lower_ratio"]),
        my_upper_ratio=float(bilinearization["my_upper_ratio"]),
    )


def _configured_phi_u(curve_points: list[MomentCurvaturePoint], config: dict[str, Any]) -> float | None:
    """Return user-defined phi_u, final phi, or None for automatic post-peak criterion."""

    ultimate = config["bilinearization"]["ultimate"]
    mode = ultimate["mode"]
    if mode == "user_defined_phi_u":
        return float(ultimate["phi_u"])
    if mode == "final_valid_point":
        return max(abs(point.phi) for point in curve_points)
    if mode == "first_post_peak_strength_drop":
        return None
    raise ValueError(f"Unsupported ultimate mode: {mode}")


def _signed_curve_rows(
    curve_id: str,
    curve_name: str,
    sign: float,
    actual_curve: list[dict[str, Any]],
    bilinear_curve: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build signed CSV rows for actual and bilinear curves."""

    actual_rows: list[dict[str, Any]] = []
    for index, point in enumerate(actual_curve):
        phi = float(point["phi"])
        moment = float(point["moment"])
        actual_rows.append(
            {
                "curve_id": curve_id,
                "curve_name": curve_name,
                "point_index": index,
                "phi": sign * phi,
                "moment": sign * moment,
                "phi_abs": phi,
                "moment_abs": moment,
            }
        )

    bilinear_rows: list[dict[str, Any]] = []
    for index, point in enumerate(bilinear_curve):
        phi = float(point["phi"])
        moment = float(point["moment"])
        bilinear_rows.append(
            {
                "curve_id": curve_id,
                "curve_name": curve_name,
                "point_index": index,
                "point": point["point"],
                "phi": sign * phi,
                "moment": sign * moment,
                "phi_abs": phi,
                "moment_abs": moment,
            }
        )
    return actual_rows, bilinear_rows


def _signed_plot_result(curve_config: dict[str, Any], result: dict[str, Any]) -> dict[str, object]:
    """Return result payload with signed curves for plotting."""

    sign = _curve_sign(curve_config)
    signed = dict(result)
    signed["curve_id"] = curve_config["id"]
    signed["name"] = curve_config["name"]
    signed["actual_curve"] = [
        {"phi": sign * float(point["phi"]), "moment": sign * float(point["moment"])}
        for point in result["actual_curve"]
    ]
    signed["bilinear_curve"] = [
        {"point": point["point"], "phi": sign * float(point["phi"]), "moment": sign * float(point["moment"])}
        for point in result["bilinear_curve"]
    ]
    return signed


def _cyclic_cut_point(
    config: dict[str, Any],
    *,
    sheet_name: str,
    curve_config: dict[str, Any],
) -> dict[str, float] | None:
    """Return the configured signed cyclic cut point for a curve, when available."""

    cyclic_config = config.get("cyclic_diagram")
    if not isinstance(cyclic_config, dict) or not bool(cyclic_config.get("enabled", False)):
        return None

    cut_points_by_sheet = cyclic_config.get("cut_points_by_sheet", {})
    if not isinstance(cut_points_by_sheet, dict):
        return None

    sheet_cut_points = cut_points_by_sheet.get(sheet_name)
    if sheet_cut_points is None:
        sheet_cut_points = cut_points_by_sheet.get(sheet_name.strip())
    if sheet_cut_points is None:
        sheet_cut_points = cut_points_by_sheet.get(_safe_sheet_folder_name(sheet_name))
    if not isinstance(sheet_cut_points, dict):
        return None

    curve_id = str(curve_config["id"])
    branch_key = "negative_bending" if str(curve_config["sign"]) == "negative" else "positive_bending"
    raw_cut = sheet_cut_points.get(curve_id, sheet_cut_points.get(branch_key))
    if not isinstance(raw_cut, dict):
        return None

    phi = _as_float(raw_cut.get("phi"))
    moment = _as_float(raw_cut.get("moment"))
    if phi is None or moment is None:
        return None
    if abs(phi) <= 1e-15:
        return None

    sign = _curve_sign(curve_config)
    return {"phi": sign * abs(phi), "moment": sign * abs(moment)}


def _cyclic_curve_points(
    curve_points: list[MomentCurvaturePoint],
    cut_point: dict[str, float],
) -> list[MomentCurvaturePoint]:
    """Return the positive M-phi curve used to recalculate the cyclic bilinearization."""

    return truncate_moment_curvature_curve_at_point(
        curve_points,
        phi_u=abs(float(cut_point["phi"])),
        moment_u=abs(float(cut_point["moment"])),
    )


def _cyclic_cut_point_rows(curve_results: list[dict[str, object]]) -> list[dict[str, Any]]:
    """Build a compact table with configured cyclic endpoints."""

    rows: list[dict[str, Any]] = []
    for result in curve_results:
        curve_id = str(result["curve_id"])
        curve_name = str(result.get("name", curve_id))
        cut_point = result.get("cyclic_cut_point")
        if isinstance(cut_point, dict):
            phi = float(cut_point["phi"])
            moment = float(cut_point["moment"])
            rows.append(
                {
                    "curve_id": curve_id,
                    "curve_name": curve_name,
                    "mode": "configured",
                    "phi": phi,
                    "moment": moment,
                    "phi_abs": abs(phi),
                    "moment_abs": abs(moment),
                    "phi_u_ciclico": phi,
                    "Mu_ciclico": moment,
                }
            )
        else:
            rows.append(
                {
                    "curve_id": curve_id,
                    "curve_name": curve_name,
                    "mode": "auto",
                    "phi": "",
                    "moment": "",
                    "phi_abs": "",
                    "moment_abs": "",
                    "phi_u_ciclico": "",
                    "Mu_ciclico": "",
                }
            )
    return rows


def _with_cyclic_cut_columns(row: dict[str, Any], cut_point: dict[str, float] | None) -> dict[str, Any]:
    """Add cyclic endpoint columns to a parameter row without changing the bilinearized values."""

    annotated = dict(row)
    if isinstance(cut_point, dict):
        phi = float(cut_point["phi"])
        moment = float(cut_point["moment"])
        annotated["cyclic_cut_phi"] = phi
        annotated["cyclic_cut_moment"] = moment
        annotated["cyclic_cut_phi_abs"] = abs(phi)
        annotated["cyclic_cut_moment_abs"] = abs(moment)
        annotated["phi_u_ciclico"] = phi
        annotated["Mu_ciclico"] = moment
    else:
        annotated["cyclic_cut_phi"] = ""
        annotated["cyclic_cut_moment"] = ""
        annotated["cyclic_cut_phi_abs"] = ""
        annotated["cyclic_cut_moment_abs"] = ""
        annotated["phi_u_ciclico"] = ""
        annotated["Mu_ciclico"] = ""
    return annotated


def _parameter_rows(curve_id: str, curve_name: str, result: dict[str, Any], sign: float) -> dict[str, Any]:
    """Build one CSV row with key bilinearization parameters."""

    parameters = result["parameters"]
    peak = result["peak"]
    area = result["area"]
    return {
        "curve_id": curve_id,
        "curve_name": curve_name,
        "Ke": parameters["Ke"],
        "My": parameters["My"],
        "phi_y": parameters["phi_y"],
        "Kp": parameters["Kp"],
        "alpha": parameters["alpha"],
        "Mu": parameters["Mu"],
        "phi_u": parameters["phi_u"],
        "signed_My": sign * float(parameters["My"]),
        "signed_phi_y": sign * float(parameters["phi_y"]),
        "signed_Mu": sign * float(parameters["Mu"]),
        "signed_phi_u": sign * float(parameters["phi_u"]),
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


def _curve_report(
    config: dict[str, Any],
    curve_config: dict[str, Any],
    result: dict[str, Any],
    *,
    sheet_name: str,
    source_workbook: Path,
    diagram_type: str = "monotonica",
    cyclic_cut_point: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build a readable YAML report for one bilinearized curve."""

    parameters = result["parameters"]
    peak = result["peak"]
    ultimate = result["ultimate"]
    area = result["area"]
    return {
        "stage_id": config["stage_id"],
        "title": config["title"],
        "model": {
            "key": "asce_fema_moment_curvature_bilinearization",
            "description": "Idealizacion bilineal ASCE/FEMA adaptada al diagrama momento-curvatura.",
        },
        "curve": {
            "id": curve_config["id"],
            "name": curve_config["name"],
            "sign": curve_config["sign"],
            "sheet": sheet_name,
            "diagram_type": diagram_type,
        },
        "units": {
            "curvature": "[1/m]",
            "moment": "[kN-m]",
            "stiffness": "[kN-m/(1/m)]",
            "area": "[kN]",
        },
        "datos_de_entrada": {
            "source_workbook": str(source_workbook),
            "sheet": sheet_name,
            "curvature_column": curve_config["curvature_column"],
            "moment_column": curve_config["moment_column"],
            "first_data_row": curve_config["first_data_row"],
            "stiffness_fraction": config["bilinearization"]["stiffness_fraction"],
            "tolerance": config["bilinearization"]["tolerance"],
            "ultimate": config["bilinearization"]["ultimate"],
            "cyclic_diagram": config.get("cyclic_diagram", {}),
            "cyclic_cut_point": cyclic_cut_point,
        },
        "datos_de_salida": {
            "M_peak": {"value": peak["moment"], "unit": "[kN-m]"},
            "phi_peak": {"value": peak["phi"], "unit": "[1/m]"},
            "phi_u": {"value": parameters["phi_u"], "unit": "[1/m]", "criterion": ultimate["mode"]},
            "Mu": {"value": parameters["Mu"], "unit": "[kN-m]", "equation": "Mu = M(phi_u)"},
            "M_60My": {"value": parameters["M_60My"], "unit": "[kN-m]", "equation": "M_60My = 0.60 * My"},
            "phi_60My": {
                "value": parameters["phi_60My"],
                "unit": "[1/m]",
                "equation": "phi_60My = phi(M_60My)",
            },
            "Ke": {"value": parameters["Ke"], "unit": "[kN-m/(1/m)]", "equation": "Ke = M_60My / phi_60My"},
            "My": {"value": parameters["My"], "unit": "[kN-m]", "criterion": "energia_equivalente"},
            "phi_y": {"value": parameters["phi_y"], "unit": "[1/m]", "equation": "phi_y = My / Ke"},
            "Kp": {"value": parameters["Kp"], "unit": "[kN-m/(1/m)]", "equation": "Kp = (Mu - My) / (phi_u - phi_y)"},
            "alpha": {"value": parameters["alpha"], "unit": "[-]", "equation": "alpha = Kp / Ke"},
            "A_real": {"value": area["A_real"], "unit": "[kN]", "equation": "A_real = integral M(phi) dphi"},
            "A_bilinear": {
                "value": area["A_bilinear"],
                "unit": "[kN]",
                "equation": "A_bilinear = 0.5*My*phi_y + 0.5*(My + Mu)*(phi_u - phi_y)",
            },
            "relative_error": {"value": parameters["relative_error"], "unit": "[-]"},
            "absolute_relative_error": {"value": parameters["absolute_relative_error"], "unit": "[-]"},
            "ductility_phi": {"value": parameters["ductility_phi"], "unit": "[-]", "equation": "mu_phi = phi_u / phi_y"},
            "constitutive_function": {
                "branches": [
                    {
                        "range": "0 <= phi <= phi_y",
                        "equation": f"M(phi) = {parameters['Ke']:.8g} * phi",
                    },
                    {
                        "range": "phi_y < phi <= phi_u",
                        "equation": (
                            f"M(phi) = {parameters['My']:.8g} "
                            f"+ ({parameters['Kp']:.8g}) * (phi - {parameters['phi_y']:.8g})"
                        ),
                    },
                ]
            },
            "status": result["status"],
        },
    }


def run(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_root: str | Path = "outputs",
) -> dict[str, Any]:
    """Run Etapa 3 section characterization."""

    prepared = prepare_stage_from_config(config_path, output_root, required_keys=REQUIRED_TOP_LEVEL_KEYS)
    config = prepared["config"]
    validate_stage_03_config(config)

    source_workbook = Path(config["source"]["workbook"])
    sheet_names = _selected_sheet_names(config, source_workbook)
    output_dirs = _reset_stage_output_root(prepared["output_dirs"]["root"], str(config["stage_id"]))
    settings = _settings_from_config(config)
    ultimate_config = config["bilinearization"]["ultimate"]
    post_peak_strength_ratio = float(ultimate_config.get("post_peak_strength_ratio", 0.80))

    sheet_summaries: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_curve_count = 0

    for sheet_name in sheet_names:
        sheet_dirs = _sheet_output_dirs(output_dirs["root"], sheet_name)
        rows = read_xlsx_rows(source_workbook, sheet_name=sheet_name)
        curve_configs = _detect_sheet_curves(rows, sheet_name, config)

        all_actual_rows: list[dict[str, Any]] = []
        all_bilinear_rows: list[dict[str, Any]] = []
        all_cyclic_actual_rows: list[dict[str, Any]] = []
        all_cyclic_bilinear_rows: list[dict[str, Any]] = []
        parameter_rows: list[dict[str, Any]] = []
        cyclic_parameter_rows: list[dict[str, Any]] = []
        report_payloads: dict[str, dict[str, Any]] = {}
        cyclic_report_payloads: dict[str, dict[str, Any]] = {}
        plot_results: list[dict[str, object]] = []
        cyclic_plot_results: list[dict[str, object]] = []
        generated_paths: dict[str, Path] = {}
        sheet_warnings: list[str] = []

        for curve_config in curve_configs:
            curve_points = _extract_curve_points(rows, curve_config)
            sign = _curve_sign(curve_config)
            result = bilinearize_moment_curvature(
                curve_points,
                phi_u=_configured_phi_u(curve_points, config),
                post_peak_strength_ratio=post_peak_strength_ratio,
                settings=settings,
            )
            if result["status"] != "converged":
                warning = (
                    f"{sheet_name}/{curve_config['id']}: bilinearization did not reach tolerance; best error = "
                    f"{result['parameters']['absolute_relative_error']:.4g}."
                )
                sheet_warnings.append(warning)
                warnings.append(warning)

            actual_rows, bilinear_rows = _signed_curve_rows(
                str(curve_config["id"]),
                str(curve_config["name"]),
                sign,
                result["actual_curve"],
                result["bilinear_curve"],
            )
            all_actual_rows.extend(actual_rows)
            all_bilinear_rows.extend(bilinear_rows)
            parameter_rows.append(_parameter_rows(str(curve_config["id"]), str(curve_config["name"]), result, sign))
            report_payloads[str(curve_config["id"])] = _curve_report(
                config,
                curve_config,
                result,
                sheet_name=sheet_name,
                source_workbook=source_workbook,
                diagram_type="monotonica",
            )
            signed_result = _signed_plot_result(curve_config, result)
            plot_results.append(signed_result)

            cyclic_cut_point = _cyclic_cut_point(config, sheet_name=sheet_name, curve_config=curve_config)
            if cyclic_cut_point is None:
                cyclic_mechanics_result = result
            else:
                cyclic_points = _cyclic_curve_points(curve_points, cyclic_cut_point)
                cyclic_mechanics_result = bilinearize_moment_curvature(
                    cyclic_points,
                    phi_u=abs(float(cyclic_cut_point["phi"])),
                    post_peak_strength_ratio=post_peak_strength_ratio,
                    settings=settings,
                )
                if cyclic_mechanics_result["status"] != "converged":
                    warning = (
                        f"{sheet_name}/{curve_config['id']}/ciclica: bilinearization did not reach tolerance; "
                        f"best error = {cyclic_mechanics_result['parameters']['absolute_relative_error']:.4g}."
                    )
                    sheet_warnings.append(warning)
                    warnings.append(warning)

            cyclic_actual_rows, cyclic_bilinear_rows = _signed_curve_rows(
                str(curve_config["id"]),
                str(curve_config["name"]),
                sign,
                cyclic_mechanics_result["actual_curve"],
                cyclic_mechanics_result["bilinear_curve"],
            )
            all_cyclic_actual_rows.extend(cyclic_actual_rows)
            all_cyclic_bilinear_rows.extend(cyclic_bilinear_rows)
            cyclic_parameter_rows.append(
                _with_cyclic_cut_columns(
                    _parameter_rows(str(curve_config["id"]), str(curve_config["name"]), cyclic_mechanics_result, sign),
                    cyclic_cut_point,
                )
            )

            cyclic_signed_result = _signed_plot_result(curve_config, cyclic_mechanics_result)
            if cyclic_cut_point is not None:
                cyclic_signed_result["cyclic_cut_point"] = cyclic_cut_point
            cyclic_plot_results.append(cyclic_signed_result)
            cyclic_report_payloads[str(curve_config["id"])] = _curve_report(
                config,
                curve_config,
                cyclic_mechanics_result,
                sheet_name=sheet_name,
                source_workbook=source_workbook,
                diagram_type="ciclica",
                cyclic_cut_point=cyclic_cut_point,
            )

        generated_paths["data_moment_curvature_curves"] = write_csv_rows(
            all_actual_rows,
            sheet_dirs["monotonica_data"] / "moment_curvature_curves.csv",
        )
        generated_paths["data_monotonica_moment_curvature_curves"] = generated_paths["data_moment_curvature_curves"]
        generated_paths["data_bilinear_curves"] = write_csv_rows(
            all_bilinear_rows,
            sheet_dirs["monotonica_data"] / "bilinear_curves.csv",
        )
        generated_paths["data_monotonica_bilinear_curves"] = generated_paths["data_bilinear_curves"]
        generated_paths["data_bilinearization_parameters"] = write_csv_rows(
            parameter_rows,
            sheet_dirs["monotonica_data"] / "bilinearization_parameters.csv",
        )
        generated_paths["data_monotonica_bilinearization_parameters"] = generated_paths[
            "data_bilinearization_parameters"
        ]

        generated_paths["data_ciclica_moment_curvature_curves"] = write_csv_rows(
            all_cyclic_actual_rows,
            sheet_dirs["ciclica_data"] / "moment_curvature_curves.csv",
        )
        generated_paths["data_ciclica_bilinear_curves"] = write_csv_rows(
            all_cyclic_bilinear_rows,
            sheet_dirs["ciclica_data"] / "bilinear_curves.csv",
        )
        generated_paths["data_ciclica_bilinearization_parameters"] = write_csv_rows(
            cyclic_parameter_rows,
            sheet_dirs["ciclica_data"] / "bilinearization_parameters.csv",
        )
        generated_paths["data_ciclica_cut_points"] = write_csv_rows(
            _cyclic_cut_point_rows(cyclic_plot_results),
            sheet_dirs["ciclica_data"] / "cyclic_cut_points.csv",
        )

        for curve_id, payload in report_payloads.items():
            generated_paths[f"report_{curve_id}_yaml"] = write_yaml_result(
                payload,
                sheet_dirs["monotonica_reports"] / curve_id / f"{curve_id}_bilinearization.yaml",
            )
            generated_paths[f"report_monotonica_{curve_id}_yaml"] = generated_paths[f"report_{curve_id}_yaml"]

        for curve_id, payload in cyclic_report_payloads.items():
            generated_paths[f"report_ciclica_{curve_id}_yaml"] = write_yaml_result(
                payload,
                sheet_dirs["ciclica_reports"] / curve_id / f"{curve_id}_bilinearization.yaml",
            )

        generated_paths["figure_moment_curvature_real"] = plot_moment_curvature_real_curves(
            plot_results,
            sheet_dirs["monotonica_figures"] / "moment_curvature_real.png",
        )
        generated_paths["figure_monotonica_moment_curvature_real"] = generated_paths["figure_moment_curvature_real"]
        generated_paths["figure_moment_curvature_bilinearization"] = plot_moment_curvature_bilinear_only(
            plot_results,
            sheet_dirs["monotonica_figures"] / "moment_curvature_bilinearization.png",
        )
        generated_paths["figure_monotonica_moment_curvature_bilinearization"] = generated_paths[
            "figure_moment_curvature_bilinearization"
        ]
        generated_paths["figure_moment_curvature_real_vs_bilinear"] = plot_moment_curvature_real_vs_bilinear(
            plot_results,
            sheet_dirs["monotonica_figures"] / "moment_curvature_real_vs_bilinear.png",
        )
        generated_paths["figure_monotonica_moment_curvature_real_vs_bilinear"] = generated_paths[
            "figure_moment_curvature_real_vs_bilinear"
        ]

        generated_paths["figure_ciclica_moment_curvature_real"] = plot_moment_curvature_real_curves(
            cyclic_plot_results,
            sheet_dirs["ciclica_figures"] / "moment_curvature_real.png",
            title="Diagrama momento-curvatura ciclico",
            subtitle="Curvas recortadas en la curvatura ultima ciclica configurada por viga",
        )
        generated_paths["figure_ciclica_moment_curvature_bilinearization"] = plot_moment_curvature_bilinear_only(
            cyclic_plot_results,
            sheet_dirs["ciclica_figures"] / "moment_curvature_bilinearization.png",
            title="Idealizacion bilineal momento-curvatura ciclica",
            subtitle="Bilinealizacion recalculada con la curva recortada al punto ciclico configurado",
        )
        generated_paths["figure_ciclica_moment_curvature_real_vs_bilinear"] = plot_moment_curvature_real_vs_bilinear(
            cyclic_plot_results,
            sheet_dirs["ciclica_figures"] / "moment_curvature_real_vs_bilinear.png",
            title="Comparacion ciclica momento-curvatura real vs bilineal",
            subtitle="Curva real recortada y bilinealizacion recalculada para el diagrama ciclico",
        )

        sheet_results_path = sheet_dirs["monotonica_data"] / "stage_03_sheet_results.json"
        cyclic_sheet_results_path = sheet_dirs["ciclica_data"] / "stage_03_sheet_results.json"
        sheet_payload = {
            "stage_id": config["stage_id"],
            "title": config["title"],
            "sheet": sheet_name,
            "sheet_output_root": sheet_dirs["root"],
            "status": "completed",
            "source": {"workbook": str(source_workbook), "sheet": sheet_name},
            "method": config["bilinearization"]["method"],
            "curve_count": len(curve_configs),
            "curves": curve_configs,
            "parameters": parameter_rows,
            "generated_files": {key: str(path) for key, path in generated_paths.items()},
            "warnings": sheet_warnings,
        }
        generated_paths["data_sheet_results_json"] = write_json_result(sheet_payload, sheet_results_path)
        generated_paths["data_monotonica_sheet_results_json"] = generated_paths["data_sheet_results_json"]
        generated_paths["data_ciclica_sheet_results_json"] = write_json_result(sheet_payload, cyclic_sheet_results_path)
        sheet_payload["results_path"] = sheet_results_path
        sheet_payload["generated_files"] = {key: str(path) for key, path in generated_paths.items()}
        write_json_result(sheet_payload, sheet_results_path)
        cyclic_sheet_payload = dict(sheet_payload)
        cyclic_sheet_payload["diagram_type"] = "ciclica"
        cyclic_sheet_payload["parameters"] = cyclic_parameter_rows
        cyclic_sheet_payload["results_path"] = cyclic_sheet_results_path
        write_json_result(cyclic_sheet_payload, cyclic_sheet_results_path)
        sheet_summaries.append(sheet_payload)
        total_curve_count += len(curve_configs)

    results_path = stage_results_json_path(output_dirs, filename="stage_03_results.json")
    result_payload = {
        "stage_id": config["stage_id"],
        "title": config["title"],
        "status": "completed",
        "config": config,
        "config_path": Path(config_path),
        "output_dirs": output_dirs,
        "source": config["source"],
        "method": config["bilinearization"]["method"],
        "sheet_count": len(sheet_summaries),
        "curve_count": total_curve_count,
        "sheets": sheet_summaries,
        "generated_files": {},
        "warnings": warnings,
    }
    stage_generated_paths = {"data_results_json": write_json_result(result_payload, results_path)}
    result_payload["results_path"] = results_path
    result_payload["generated_files"] = {key: str(path) for key, path in stage_generated_paths.items()}
    write_json_result(result_payload, results_path)
    return result_payload

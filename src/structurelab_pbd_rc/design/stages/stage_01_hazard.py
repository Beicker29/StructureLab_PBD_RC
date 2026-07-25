"""Flujo de Etapa 1: calculo de amenaza mediante casos independientes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import shutil
from typing import Any

from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.design.stages._base import prepare_stage_from_config, write_stage_table_pair
from structurelab_pbd_rc.io.etabs import write_etabs_response_spectrum_txt
from structurelab_pbd_rc.io.paths import stage_results_json_path
from structurelab_pbd_rc.io.write_results import write_json_result, write_yaml_result
from structurelab_pbd_rc.mechanics.hazard.seismic.spectra import (
    CCP14SpectrumParameters,
    NSR10SpectrumParameters,
    ccp14_spectral_acceleration,
    ccp14_spectrum,
    ccp14_transition_parameters,
    generate_period_vector,
    nsr10_spectral_acceleration,
    nsr10_spectrum,
    nsr10_transition_parameters,
    validate_site_profile,
)
from structurelab_pbd_rc.reports.plots import (
    COLOR_CYCLE,
    plot_response_spectra,
    plot_response_spectrum_with_notable_points,
)
from structurelab_pbd_rc.reports.stage_01_hazard_report import write_stage_01_pdf_report_from_yaml

DEFAULT_CONFIG_PATH = Path("configs/stage_01/case_01_nsr10_spectra.yaml")

REQUIRED_TOP_LEVEL_KEYS = ("stage_id", "case_id", "title", "units", "hazard")
EXPECTED_RETURN_PERIODS = {31, 475, 2500}
HAZARD_LEVEL_KEYS = ("service", "design", "maximum_considered")
HAZARD_LEVEL_LABELS = {
    "service": "Servicio",
    "design": "Diseno",
    "maximum_considered": "Maximo considerado",
}
HAZARD_LEVEL_COLORS = {
    "service": COLOR_CYCLE[0],
    "design": COLOR_CYCLE[1],
    "maximum_considered": COLOR_CYCLE[2],
}
HAZARD_LEVEL_FILENAME_PARTS = {
    "service": "service_31",
    "design": "design_475",
    "maximum_considered": "maximum_considered_2500",
}
CASE_OUTPUT_FOLDERS = {
    "case_01_nsr10": "nsr10_spectra",
    "case_02_sgc_ccp14": "ccp14_spectra",
}
LEGACY_STAGE_LEVEL_OUTPUT_DIRS = ("data", "figures", "reports")


def _as_float(value: Any, *, name: str) -> float:
    """Return a config value as float with a clear error."""

    if value is None or value == "":
        raise ValueError(f"Missing required numeric value: {name}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value!r}") from exc


def _as_int(value: Any, *, name: str) -> int:
    """Return a config value as int with a clear error."""

    if value is None or value == "":
        raise ValueError(f"Missing required integer value: {name}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value for {name}: {value!r}") from exc
    return number


def _validate_units(units: dict[str, Any]) -> None:
    require_keys(units, ["period", "spectral_acceleration"], context="units")
    if units["period"] != "s":
        raise ValueError("Unsupported period unit: expected s")
    if units["spectral_acceleration"] != "g":
        raise ValueError("Unsupported spectral acceleration unit: expected g")


def _seismic_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return the seismic hazard block from a stage 1 config."""

    require_keys(config["hazard"], ["seismic"], context="hazard")
    seismic = config["hazard"]["seismic"]
    if not isinstance(seismic, dict):
        raise ValueError("hazard.seismic must be a mapping.")
    return seismic


def _periods_from_config(config: dict[str, Any]) -> list[float]:
    seismic = _seismic_config(config)
    require_keys(seismic, ["period_range"], context="hazard.seismic")
    require_keys(seismic["period_range"], ["start", "end", "step"], context="hazard.seismic.period_range")
    return generate_period_vector(
        _as_float(seismic["period_range"]["start"], name="hazard.seismic.period_range.start"),
        _as_float(seismic["period_range"]["end"], name="hazard.seismic.period_range.end"),
        _as_float(seismic["period_range"]["step"], name="hazard.seismic.period_range.step"),
    )


def _reset_directory(path: Path, *, expected_parent: Path) -> None:
    """Delete one known output directory after checking its resolved parent."""

    if not path.exists():
        return
    resolved = path.resolve()
    if resolved.parent != expected_parent.resolve():
        raise ValueError(f"Refusing to reset unexpected output directory: {resolved}")
    if resolved.is_dir():
        shutil.rmtree(resolved)
    else:
        resolved.unlink()


def _case_output_dirs(stage_root: Path, folder_name: str) -> dict[str, Path]:
    """Create output directories for one Stage 1 spectrum case."""

    root = stage_root / folder_name
    dirs = {"root": root, "data": root / "data", "figures": root / "figures", "reports": root / "reports"}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _prepare_stage_01_output_dirs(stage_root: Path, active_case_id: str) -> dict[str, dict[str, Path]]:
    """Create the two spectrum folders and reset only the active case."""

    stage_root.mkdir(parents=True, exist_ok=True)
    for legacy_dir in LEGACY_STAGE_LEVEL_OUTPUT_DIRS:
        _reset_directory(stage_root / legacy_dir, expected_parent=stage_root)

    case_dirs: dict[str, dict[str, Path]] = {}
    for case_id, folder_name in CASE_OUTPUT_FOLDERS.items():
        case_root = stage_root / folder_name
        if case_id == active_case_id:
            _reset_directory(case_root, expected_parent=stage_root)
        case_dirs[case_id] = _case_output_dirs(stage_root, folder_name)
    return case_dirs


def _preserve_empty_case_dirs(case_dirs_by_id: dict[str, dict[str, Path]]) -> None:
    """Add .gitkeep only to empty case subdirectories."""

    for dirs in case_dirs_by_id.values():
        for name in ("data", "figures", "reports"):
            path = dirs[name]
            if not any(path.iterdir()):
                (path / ".gitkeep").write_text("", encoding="utf-8")


def validate_stage_01_config(config: dict[str, Any]) -> None:
    """Validate the editable structure required by Etapa 1."""

    require_keys(config, REQUIRED_TOP_LEVEL_KEYS, context="stage_01 configuration")
    if config["stage_id"] != "stage_01":
        raise ValueError("stage_id must be stage_01")
    _validate_units(config["units"])
    _periods_from_config(config)
    case_id = str(config["case_id"])
    if case_id == "case_01_nsr10":
        _validate_case_01_config(config)
    elif case_id == "case_02_sgc_ccp14":
        _validate_case_02_config(config)
    else:
        raise ValueError(f"Unsupported stage_01 case_id: {case_id}")


def _validate_case_01_config(config: dict[str, Any]) -> None:
    seismic = _seismic_config(config)
    require_keys(seismic, ["source", "nsr10_parameters", "hazard_levels"], context="hazard.seismic")
    require_keys(
        seismic["nsr10_parameters"],
        ["Aa", "Av", "Fa", "Fv", "importance_factor", "soil_profile"],
        context="hazard.seismic.nsr10_parameters",
    )
    levels = seismic["hazard_levels"]
    require_keys(levels, HAZARD_LEVEL_KEYS, context="hazard.seismic.hazard_levels")
    periods = {
        _as_int(
            levels["service"]["return_period_years"],
            name="hazard.seismic.hazard_levels.service.return_period_years",
        ),
        _as_int(
            levels["design"]["return_period_years"],
            name="hazard.seismic.hazard_levels.design.return_period_years",
        ),
        _as_int(
            levels["maximum_considered"]["return_period_years"],
            name="hazard.seismic.hazard_levels.maximum_considered.return_period_years",
        ),
    }
    if periods != EXPECTED_RETURN_PERIODS:
        raise ValueError("Case 1 return periods must be exactly 31, 475 and 2500 years.")
    for key in HAZARD_LEVEL_KEYS:
        scale = _as_float(levels[key]["scale_factor"], name=f"hazard.seismic.hazard_levels.{key}.scale_factor")
        if scale <= 0:
            raise ValueError(f"hazard.seismic.hazard_levels.{key}.scale_factor must be positive.")


def _validate_case_02_config(config: dict[str, Any]) -> None:
    seismic = _seismic_config(config)
    require_keys(seismic, ["source", "site", "hazard_levels"], context="hazard.seismic")
    require_keys(seismic["site"], ["profile"], context="hazard.seismic.site")
    validate_site_profile(str(seismic["site"]["profile"]))
    levels = seismic["hazard_levels"]
    require_keys(levels, HAZARD_LEVEL_KEYS, context="hazard.seismic.hazard_levels")

    missing: list[str] = []
    periods: set[int] = set()
    for level_key in HAZARD_LEVEL_KEYS:
        record = levels[level_key]
        context = f"hazard.seismic.hazard_levels.{level_key}"
        for key in ("return_period_years", "PGA", "Sa_0_2", "Sa_1_0"):
            if record.get(key) is None or record.get(key) == "":
                missing.append(f"{context}.{key}")
        if record.get("return_period_years") is not None:
            periods.add(_as_int(record["return_period_years"], name=f"{context}.return_period_years"))
    if missing:
        raise ValueError("Missing SGC hazard parameters: " + ", ".join(missing))
    if periods != EXPECTED_RETURN_PERIODS:
        raise ValueError("Case 2 return periods must be exactly 31, 475 and 2500 years.")
    for level_key in HAZARD_LEVEL_KEYS:
        record = levels[level_key]
        context = f"hazard.seismic.hazard_levels.{level_key}"
        for key in ("PGA", "Sa_0_2", "Sa_1_0"):
            value = _as_float(record[key], name=f"{context}.{key}")
            if value < 0:
                raise ValueError(f"{context}.{key} must be non-negative.")
        if _as_float(record["Sa_0_2"], name=f"{context}.Sa_0_2") <= 0:
            raise ValueError(f"{context}.Sa_0_2 must be positive.")
        if _as_float(record["Sa_1_0"], name=f"{context}.Sa_1_0") <= 0:
            raise ValueError(f"{context}.Sa_1_0 must be positive.")


def _case_01_parameters_rows(config: dict[str, Any], parameters: NSR10SpectrumParameters) -> list[dict[str, Any]]:
    levels = _seismic_config(config)["hazard_levels"]
    return [
        {"parameter": "Aa", "value": parameters.Aa, "unit": "g", "equation": "input"},
        {"parameter": "Av", "value": parameters.Av, "unit": "g", "equation": "input"},
        {"parameter": "Fa", "value": parameters.Fa, "unit": "-", "equation": "input"},
        {"parameter": "Fv", "value": parameters.Fv, "unit": "-", "equation": "input"},
        {"parameter": "I", "value": parameters.importance_factor, "unit": "-", "equation": "input"},
        {"parameter": "T0", "value": parameters.T0, "unit": "s", "equation": "0.1 * Av * Fv / (Aa * Fa)"},
        {"parameter": "Tc", "value": parameters.Tc, "unit": "s", "equation": "0.48 * Av * Fv / (Aa * Fa)"},
        {"parameter": "TL", "value": parameters.TL, "unit": "s", "equation": "2.4 * Fv"},
        {"parameter": "Sa_plateau", "value": parameters.Sa_plateau, "unit": "g", "equation": "2.5 * Aa * Fa * I"},
        {
            "parameter": "F_31",
            "value": levels["service"]["scale_factor"],
            "unit": "-",
            "equation": "Sa_31(T) = F_31 * Sa_475(T)",
        },
        {
            "parameter": "F_2500",
            "value": levels["maximum_considered"]["scale_factor"],
            "unit": "-",
            "equation": "Sa_2500(T) = F_2500 * Sa_475(T)",
        },
    ]


def _nsr10_notable_points(parameters: NSR10SpectrumParameters, scale_factor: float) -> list[dict[str, Any]]:
    """Return notable points for one scaled NSR-10 spectrum."""

    return [
        {
            "label": "Sa(0)",
            "period": 0.0,
            "value": scale_factor * nsr10_spectral_acceleration(0.0, parameters),
            "legend_label": (
                f"Arranque: T = 0.000 [s], Sa = "
                f"{scale_factor * nsr10_spectral_acceleration(0.0, parameters):.4g} [g]"
            ),
        },
        {
            "label": "T0",
            "period": parameters.T0,
            "value": scale_factor * nsr10_spectral_acceleration(parameters.T0, parameters),
            "legend_label": (
                f"T0 = {parameters.T0:.4g} [s], Sa = "
                f"{scale_factor * nsr10_spectral_acceleration(parameters.T0, parameters):.4g} [g]"
            ),
        },
        {
            "label": "Tc",
            "period": parameters.Tc,
            "value": scale_factor * nsr10_spectral_acceleration(parameters.Tc, parameters),
            "legend_label": (
                f"Tc = {parameters.Tc:.4g} [s], Sa = "
                f"{scale_factor * nsr10_spectral_acceleration(parameters.Tc, parameters):.4g} [g]"
            ),
        },
        {
            "label": "TL",
            "period": parameters.TL,
            "value": scale_factor * nsr10_spectral_acceleration(parameters.TL, parameters),
            "legend_label": (
                f"TL = {parameters.TL:.4g} [s], Sa = "
                f"{scale_factor * nsr10_spectral_acceleration(parameters.TL, parameters):.4g} [g]"
            ),
        },
    ]


def _ccp14_notable_points(parameters: CCP14SpectrumParameters) -> list[dict[str, Any]]:
    """Return notable points for one CCP-14 spectrum."""

    return [
        {
            "label": "As",
            "period": 0.0,
            "value": ccp14_spectral_acceleration(0.0, parameters),
            "legend_label": f"As = {parameters.As:.4g} [g] en T = 0.000 [s]",
        },
        {
            "label": "T0",
            "period": parameters.T0,
            "value": ccp14_spectral_acceleration(parameters.T0, parameters),
            "legend_label": f"T0 = {parameters.T0:.4g} [s], Csm = {parameters.SDS:.4g} [g]",
        },
        {
            "label": "Ts",
            "period": parameters.Ts,
            "value": ccp14_spectral_acceleration(parameters.Ts, parameters),
            "legend_label": f"Ts = {parameters.Ts:.4g} [s], Csm = {parameters.SDS:.4g} [g]",
        },
        {
            "label": "T = 1.0 s",
            "period": 1.0,
            "value": ccp14_spectral_acceleration(1.0, parameters),
            "legend_label": f"T = 1.000 [s], Csm = {ccp14_spectral_acceleration(1.0, parameters):.4g} [g]",
        },
    ]


def _write_etabs_spectrum_files(
    rows: list[dict[str, Any]],
    data_dir: Path,
    *,
    case_prefix: str,
    level_specs: list[tuple[str, str]],
) -> dict[str, Path]:
    """Write one ETABS-ready TXT file per spectrum level."""

    etabs_dir = data_dir / "etabs"
    generated_files: dict[str, Path] = {}
    for level_key, value_key in level_specs:
        filename_level = HAZARD_LEVEL_FILENAME_PARTS[level_key]
        generated_files[f"{case_prefix}_{level_key}_etabs_txt"] = write_etabs_response_spectrum_txt(
            rows,
            etabs_dir / f"{case_prefix}_{filename_level}_etabs_v22.txt",
            period_key="period_s",
            value_key=value_key,
        )
    return generated_files


def _run_case_01(config: dict[str, Any], output_dirs: dict[str, Path]) -> dict[str, Any]:
    periods = _periods_from_config(config)
    seismic = _seismic_config(config)
    params_config = seismic["nsr10_parameters"]
    parameters = nsr10_transition_parameters(
        Aa=_as_float(params_config["Aa"], name="hazard.seismic.nsr10_parameters.Aa"),
        Av=_as_float(params_config["Av"], name="hazard.seismic.nsr10_parameters.Av"),
        Fa=_as_float(params_config["Fa"], name="hazard.seismic.nsr10_parameters.Fa"),
        Fv=_as_float(params_config["Fv"], name="hazard.seismic.nsr10_parameters.Fv"),
        importance_factor=_as_float(
            params_config["importance_factor"], name="hazard.seismic.nsr10_parameters.importance_factor"
        ),
    )
    base = nsr10_spectrum(periods, parameters)
    levels = seismic["hazard_levels"]
    service_factor = _as_float(
        levels["service"]["scale_factor"], name="hazard.seismic.hazard_levels.service.scale_factor"
    )
    design_factor = _as_float(
        levels["design"]["scale_factor"], name="hazard.seismic.hazard_levels.design.scale_factor"
    )
    maximum_factor = _as_float(
        levels["maximum_considered"]["scale_factor"],
        name="hazard.seismic.hazard_levels.maximum_considered.scale_factor",
    )

    rows = [
        {
            "period_s": period,
            "Sa_servicio_31": service_factor * value,
            "Sa_diseno_475": design_factor * value,
            "Sa_maximo_considerado_2500": maximum_factor * value,
        }
        for period, value in zip(periods, base)
    ]
    parameter_rows = _case_01_parameters_rows(config, parameters)

    generated_files: dict[str, Path] = {}
    data_dir = output_dirs["data"]
    figures_dir = output_dirs["figures"]
    reports_dir = output_dirs["reports"]
    generated_files.update(
        write_stage_table_pair(
            rows,
            data_dir,
            filename_stem="case_01_nsr10_spectra",
            sheet_name="case_01_spectra",
            key_prefix="case_01_spectra",
        )
    )
    generated_files.update(
        write_stage_table_pair(
            parameter_rows,
            data_dir,
            filename_stem="case_01_nsr10_parameters",
            sheet_name="case_01_parameters",
            key_prefix="case_01_parameters",
        )
    )
    generated_files.update(
        _write_etabs_spectrum_files(
            rows,
            data_dir,
            case_prefix="case_01_nsr10",
            level_specs=[
                ("service", "Sa_servicio_31"),
                ("design", "Sa_diseno_475"),
                ("maximum_considered", "Sa_maximo_considerado_2500"),
            ],
        )
    )
    generated_files["case_01_spectra_figure"] = plot_response_spectra(
        rows,
        figures_dir / "case_01_nsr10_spectra.png",
        period_key="period_s",
        series=[
            {"key": "Sa_servicio_31", "label": "Servicio, Tr = 31 anos"},
            {"key": "Sa_diseno_475", "label": "Diseno, Tr = 475 anos"},
            {"key": "Sa_maximo_considerado_2500", "label": "Maximo considerado, Tr = 2500 anos"},
        ],
        title="Caso 1 - Espectros NSR-10",
        subtitle="Espectro base NSR-10 de 475 anos escalado para 31 y 2500 anos",
    )
    case_01_individual_specs = [
        ("service", "Sa_servicio_31", service_factor),
        ("design", "Sa_diseno_475", design_factor),
        ("maximum_considered", "Sa_maximo_considerado_2500", maximum_factor),
    ]
    for level_key, series_key, scale_factor in case_01_individual_specs:
        level = levels[level_key]
        label = HAZARD_LEVEL_LABELS[level_key]
        generated_files[f"case_01_{level_key}_spectrum_figure"] = plot_response_spectrum_with_notable_points(
            rows,
            figures_dir / f"case_01_nsr10_{level_key}_spectrum.png",
            period_key="period_s",
            value_key=series_key,
            title=f"NSR-10 - {label}",
            subtitle=f"Periodo de retorno Tr = {int(level['return_period_years'])} anos",
            notable_points=_nsr10_notable_points(parameters, scale_factor),
            curve_color=HAZARD_LEVEL_COLORS[level_key],
        )
    report = {
        "stage_id": "stage_01",
        "case_id": "case_01_nsr10",
        "title": config["title"],
        "datos_de_entrada": {
            "units": config["units"],
            "hazard": {"seismic": seismic},
        },
        "datos_de_salida": {
            "transition_parameters": asdict(parameters),
            "equations": {
                "T0": "T0 = 0.1 * Av * Fv / (Aa * Fa)",
                "Tc": "Tc = 0.48 * Av * Fv / (Aa * Fa)",
                "TL": "TL = 2.4 * Fv",
                "Sa_T_less_T0": "Sa = 2.5 * Aa * Fa * I * (0.4 + 0.6 * T / T0)",
                "Sa_T0_to_Tc": "Sa = 2.5 * Aa * Fa * I",
                "Sa_Tc_to_TL": "Sa = 1.2 * Av * Fv * I / T",
                "Sa_T_greater_TL": "Sa = 1.2 * Av * Fv * TL * I / T^2",
                "service_scaling": "Sa_31(T) = F_31 * Sa_475(T)",
                "maximum_scaling": "Sa_2500(T) = F_2500 * Sa_475(T)",
            },
            "rows_count": len(rows),
        },
        "generated_files": generated_files,
    }
    generated_files["case_01_report_yaml"] = reports_dir / "case_01_nsr10_report.yaml"
    write_yaml_result(report, generated_files["case_01_report_yaml"])
    generated_files.update(write_stage_01_pdf_report_from_yaml(generated_files["case_01_report_yaml"]))
    report["generated_files"] = generated_files
    write_yaml_result(report, generated_files["case_01_report_yaml"])
    return {
        "case_id": "case_01_nsr10",
        "periods": periods,
        "spectrum_rows": rows,
        "parameter_rows": parameter_rows,
        "transition_parameters": asdict(parameters),
        "generated_files": generated_files,
    }


def _case_02_parameter_rows(parameters_by_period: list[CCP14SpectrumParameters]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parameters in parameters_by_period:
        rows.append(
            {
                "return_period_years": parameters.return_period_years,
                "PGA": parameters.PGA,
                "Sa_0_2": parameters.Ss,
                "Sa_1_0": parameters.S1,
                "Fpga": parameters.Fpga,
                "Fa": parameters.Fa,
                "Fv": parameters.Fv,
                "As": parameters.As,
                "SDS": parameters.SDS,
                "SD1": parameters.SD1,
                "T0": parameters.T0,
                "Ts": parameters.Ts,
                "Sa_at_T_0": ccp14_spectral_acceleration(0.0, parameters),
                "Sa_at_T_0_2": ccp14_spectral_acceleration(0.2, parameters),
                "Sa_at_T_1_0": ccp14_spectral_acceleration(1.0, parameters),
                "units": "g, s",
                "source": "SGC hazard values with CCP-14 interpolated site factors",
            }
        )
    return rows


def _ordered_case_02_levels(seismic: dict[str, Any]) -> list[dict[str, Any]]:
    """Return CCP-14 hazard levels in the standard stage order."""

    return [seismic["hazard_levels"][level_key] for level_key in HAZARD_LEVEL_KEYS]


def _run_case_02(config: dict[str, Any], output_dirs: dict[str, Path]) -> dict[str, Any]:
    periods = _periods_from_config(config)
    seismic = _seismic_config(config)
    site_profile = str(seismic["site"]["profile"])
    ordered_records = _ordered_case_02_levels(seismic)
    parameters_by_period = [
        ccp14_transition_parameters(
            return_period_years=_as_int(record["return_period_years"], name="return_period_years"),
            PGA=_as_float(record["PGA"], name=f"hazard.seismic.hazard_levels.{level_key}.PGA"),
            Ss=_as_float(
                record["Sa_0_2"], name=f"hazard.seismic.hazard_levels.{level_key}.Sa_0_2"
            ),
            S1=_as_float(
                record["Sa_1_0"], name=f"hazard.seismic.hazard_levels.{level_key}.Sa_1_0"
            ),
            site_profile=site_profile,
        )
        for level_key, record in zip(HAZARD_LEVEL_KEYS, ordered_records)
    ]
    spectra_by_period = {
        parameters.return_period_years: ccp14_spectrum(periods, parameters) for parameters in parameters_by_period
    }
    rows = []
    for index, period in enumerate(periods):
        rows.append(
            {
                "period_s": period,
                "Sa_SGC_CCP14_31": spectra_by_period[31][index],
                "Sa_SGC_CCP14_475": spectra_by_period[475][index],
                "Sa_SGC_CCP14_2500": spectra_by_period[2500][index],
            }
        )
    parameter_rows = _case_02_parameter_rows(parameters_by_period)

    generated_files: dict[str, Path] = {}
    data_dir = output_dirs["data"]
    figures_dir = output_dirs["figures"]
    reports_dir = output_dirs["reports"]
    generated_files.update(
        write_stage_table_pair(
            rows,
            data_dir,
            filename_stem="case_02_sgc_ccp14_spectra",
            sheet_name="case_02_spectra",
            key_prefix="case_02_spectra",
        )
    )
    generated_files.update(
        write_stage_table_pair(
            parameter_rows,
            data_dir,
            filename_stem="case_02_sgc_ccp14_parameters",
            sheet_name="case_02_parameters",
            key_prefix="case_02_parameters",
        )
    )
    generated_files.update(
        _write_etabs_spectrum_files(
            rows,
            data_dir,
            case_prefix="case_02_sgc_ccp14",
            level_specs=[
                ("service", "Sa_SGC_CCP14_31"),
                ("design", "Sa_SGC_CCP14_475"),
                ("maximum_considered", "Sa_SGC_CCP14_2500"),
            ],
        )
    )
    generated_files["case_02_spectra_figure"] = plot_response_spectra(
        rows,
        figures_dir / "case_02_sgc_ccp14_spectra.png",
        period_key="period_s",
        series=[
            {"key": "Sa_SGC_CCP14_31", "label": "SGC + CCP-14, Tr = 31 anos"},
            {"key": "Sa_SGC_CCP14_475", "label": "SGC + CCP-14, Tr = 475 anos"},
            {"key": "Sa_SGC_CCP14_2500", "label": "SGC + CCP-14, Tr = 2500 anos"},
        ],
        title="Caso 2 - Espectros SGC con forma CCP-14",
        subtitle="Factores Fpga, Fa y Fv calculados por interpolacion tabular",
    )
    case_02_individual_specs = [
        ("service", "Sa_SGC_CCP14_31", parameters_by_period[0]),
        ("design", "Sa_SGC_CCP14_475", parameters_by_period[1]),
        ("maximum_considered", "Sa_SGC_CCP14_2500", parameters_by_period[2]),
    ]
    for level_key, series_key, parameters in case_02_individual_specs:
        label = HAZARD_LEVEL_LABELS[level_key]
        generated_files[f"case_02_{level_key}_spectrum_figure"] = plot_response_spectrum_with_notable_points(
            rows,
            figures_dir / f"case_02_sgc_ccp14_{level_key}_spectrum.png",
            period_key="period_s",
            value_key=series_key,
            title=f"SGC + CCP-14 - {label}",
            subtitle=f"Periodo de retorno Tr = {parameters.return_period_years} anos",
            notable_points=_ccp14_notable_points(parameters),
            curve_color=HAZARD_LEVEL_COLORS[level_key],
        )
    report = {
        "stage_id": "stage_01",
        "case_id": "case_02_sgc_ccp14",
        "title": config["title"],
        "datos_de_entrada": {
            "units": config["units"],
            "hazard": {"seismic": seismic},
        },
        "datos_de_salida": {
            "parameters_by_return_period": [asdict(parameters) for parameters in parameters_by_period],
            "equations": {
                "Fpga": "Interpolacion lineal de Tabla 3.10.3.2-1 con PGA y tipo de perfil",
                "Fa": "Interpolacion lineal de Tabla 3.10.3.2-2 con Ss y tipo de perfil",
                "Fv": "Interpolacion lineal de Tabla 3.10.3.2-3 con S1 y tipo de perfil",
                "As": "As = Fpga * PGA",
                "SDS": "SDS = Fa * Ss",
                "SD1": "SD1 = Fv * S1",
                "Ts": "Ts = SD1 / SDS",
                "T0": "T0 = 0.2 * Ts",
                "Csm_initial": "Csm = As + (SDS - As) * (T / T0)",
                "Csm_plateau": "Csm = SDS",
                "Csm_descending": "Csm = SD1 / T",
            },
            "rows_count": len(rows),
        },
        "generated_files": generated_files,
    }
    generated_files["case_02_report_yaml"] = reports_dir / "case_02_sgc_ccp14_report.yaml"
    write_yaml_result(report, generated_files["case_02_report_yaml"])
    generated_files.update(write_stage_01_pdf_report_from_yaml(generated_files["case_02_report_yaml"]))
    report["generated_files"] = generated_files
    write_yaml_result(report, generated_files["case_02_report_yaml"])
    return {
        "case_id": "case_02_sgc_ccp14",
        "periods": periods,
        "spectrum_rows": rows,
        "parameter_rows": parameter_rows,
        "transition_parameters": [asdict(parameters) for parameters in parameters_by_period],
        "generated_files": generated_files,
    }


def run(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_root: str | Path = "outputs",
) -> dict[str, Any]:
    """Run one Stage 1 hazard case from its YAML config."""

    result = prepare_stage_from_config(
        config_path,
        output_root=output_root,
        required_keys=REQUIRED_TOP_LEVEL_KEYS,
        output_subdirectories=(),
    )
    validate_stage_01_config(result["config"])
    stage_output_dirs = result["output_dirs"]
    case_id = str(result["config"]["case_id"])
    case_output_dirs_by_id = _prepare_stage_01_output_dirs(stage_output_dirs["root"], case_id)
    case_output_dirs = case_output_dirs_by_id[case_id]

    if case_id == "case_01_nsr10":
        case_result = _run_case_01(result["config"], case_output_dirs)
    elif case_id == "case_02_sgc_ccp14":
        case_result = _run_case_02(result["config"], case_output_dirs)
    else:
        raise ValueError(f"Unsupported stage_01 case_id: {case_id}")

    generated_files = dict(case_result["generated_files"])
    results_path = stage_results_json_path(case_output_dirs, filename="stage_01_results.json")
    generated_files["data_results_json"] = results_path
    output_dirs = {
        "root": stage_output_dirs["root"],
        "nsr10_spectra": case_output_dirs_by_id["case_01_nsr10"]["root"],
        "ccp14_spectra": case_output_dirs_by_id["case_02_sgc_ccp14"]["root"],
        "active_case_root": case_output_dirs["root"],
        "active_case_data": case_output_dirs["data"],
        "active_case_figures": case_output_dirs["figures"],
        "active_case_reports": case_output_dirs["reports"],
    }
    payload = {
        "stage_id": "stage_01",
        "case_id": case_id,
        "title": result["config"]["title"],
        "status": "completed",
        "config": result["config"],
        "config_path": Path(config_path),
        "output_dirs": output_dirs,
        "generated_files": generated_files,
        "warnings": [],
        "case_result": {
            key: value
            for key, value in case_result.items()
            if key not in {"spectrum_rows", "periods"}
        },
    }
    write_json_result(payload, results_path)
    _preserve_empty_case_dirs(case_output_dirs_by_id)
    payload["generated_files"] = generated_files
    payload["results_path"] = results_path
    payload["output_dirs"] = output_dirs
    payload["warnings"] = []
    return payload

"""Workflow for Taller 1: material characterization."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from structurelab_pbd_rc.core.curves import curve_rows
from structurelab_pbd_rc.core.validation import require_keys, require_positive, require_value_with_unit
from structurelab_pbd_rc.geometry.confined_core import derive_confined_core_from_cover
from structurelab_pbd_rc.geometry.rebar_layouts import RebarLayout
from structurelab_pbd_rc.geometry.reinforced_concrete import ReinforcedConcreteSection
from structurelab_pbd_rc.geometry.sections import RectangularSection
from structurelab_pbd_rc.geometry.transverse_reinforcement import TransverseReinforcement
from structurelab_pbd_rc.io.paths import workshop_results_json_path
from structurelab_pbd_rc.io.write_results import write_csv_rows, write_json_result
from structurelab_pbd_rc.materials.concrete.attard_setunge import AttardSetungeConcreteModel, AttardSetungeParameters
from structurelab_pbd_rc.materials.concrete.confinement import (
    RectangularConfinementGeometry,
    calculate_rectangular_confinement_parameters,
)
from structurelab_pbd_rc.materials.concrete.mander_adjusted import ManderAdjustedConcreteModel, ManderAdjustedParameters
from structurelab_pbd_rc.materials.concrete.mander_classic import ManderClassicConcreteModel, ManderClassicParameters
from structurelab_pbd_rc.materials.concrete.unconfined import UnconfinedConcreteModel, UnconfinedConcreteParameters
from structurelab_pbd_rc.materials.library.mesh_database import get_mesh_properties, mesh_diameter_exists
from structurelab_pbd_rc.materials.library.rebar_database import get_rebar_properties, rebar_exists
from structurelab_pbd_rc.materials.steel.buckling_models import BarBucklingParameters, BucklingSteelCompressionModel
from structurelab_pbd_rc.materials.steel.compression_models import SteelCompressionModel, SteelCompressionParameters
from structurelab_pbd_rc.materials.steel.tension_models import ManderSteelTensionModel, SteelTensionParameters
from structurelab_pbd_rc.materials.steel.welded_wire_mesh import CarrilloWeldedWireMeshModel, WeldedWireMeshParameters
from structurelab_pbd_rc.performance.ductility import calculate_curve_metrics_table
from structurelab_pbd_rc.reporting.export_excel import write_xlsx
from structurelab_pbd_rc.reporting.export_pdf import export_report_to_pdf
from structurelab_pbd_rc.reporting.plots import plot_confined_core_sketch, plot_stress_strain_curves
from structurelab_pbd_rc.reporting.tables import build_assumptions_table, build_material_parameter_table
from structurelab_pbd_rc.workflows._base import prepare_workshop_from_config

DEFAULT_CONFIG_PATH = Path("configs/workshops/workshop_01_material_characterization.yaml")

REQUIRED_TOP_LEVEL_KEYS = (
    "source_reference",
    "base_section",
    "concrete",
    "longitudinal_reinforcement",
    "transverse_reinforcement",
    "welded_wire_mesh",
    "outputs",
)

PENDING_WORK_ITEMS = {
    "geometry": [
        "TODO: definir geometria de nucleo confinado.",
        "TODO: calcular cuantia volumetrica.",
        "TODO: calcular factor de efectividad de confinamiento.",
    ],
    "concrete_models": [
        "TODO: implementar modelo de Mander clasico.",
        "TODO: implementar modelo de Mander ajustado.",
        "TODO: implementar modelo de Attard-Setunge.",
    ],
    "steel_models": [
        "TODO: implementar modelo de acero en traccion.",
        "TODO: implementar modelo de acero en compresion con pandeo.",
        "TODO: implementar modelo de malla electrosoldada.",
    ],
    "reporting": [
        "TODO: calcular metricas comparativas.",
        "TODO: generar graficas.",
        "TODO: generar tablas.",
        "TODO: construir reporte.",
    ],
}

AVAILABLE_MODELS = {
    "unconfined_concrete",
    "mander_classic",
    "mander_adjusted",
    "attard_setunge",
    "steel_tension",
    "steel_compression_no_buckling",
    "steel_compression_with_buckling",
    "welded_wire_mesh",
}


def validate_workshop_01_config(config: dict[str, Any]) -> None:
    """Validate the minimum editable structure required by Taller 1."""

    require_keys(config, REQUIRED_TOP_LEVEL_KEYS, context="workshop_01 configuration")
    require_keys(config["base_section"], ["type", "dimensions", "clear_cover_to_tie"], context="base_section")
    require_keys(config["base_section"]["dimensions"], ["width", "height"], context="base_section.dimensions")
    require_value_with_unit(config["base_section"]["dimensions"]["width"], name="base_section.width", allowed_units=["cm"])
    require_value_with_unit(config["base_section"]["dimensions"]["height"], name="base_section.height", allowed_units=["cm"])
    require_value_with_unit(config["base_section"]["clear_cover_to_tie"], name="base_section.clear_cover_to_tie", allowed_units=["cm"])
    require_keys(config["concrete"], ["compressive_strength", "elastic_modulus"], context="concrete")
    require_value_with_unit(config["concrete"]["compressive_strength"], name="concrete.compressive_strength", allowed_units=["MPa"])
    require_keys(
        config["longitudinal_reinforcement"],
        ["count", "bar_mark", "diameter", "steel"],
        context="longitudinal_reinforcement",
    )
    require_positive(float(config["longitudinal_reinforcement"]["count"]), name="longitudinal_reinforcement.count")
    if not rebar_exists(str(config["longitudinal_reinforcement"]["bar_mark"])):
        get_rebar_properties(str(config["longitudinal_reinforcement"]["bar_mark"]))
    require_keys(
        config["longitudinal_reinforcement"]["steel"],
        [
            "expected_yield_strength",
            "yield_strain",
            "elastic_modulus",
            "hardening_start_stress",
            "ultimate_strength",
            "ultimate_strain",
            "strain_hardening",
        ],
        context="longitudinal_reinforcement.steel",
    )
    require_keys(
        config["transverse_reinforcement"],
        ["type", "bar_mark", "diameter", "spacing", "expected_yield_strength"],
        context="transverse_reinforcement",
    )
    require_value_with_unit(config["transverse_reinforcement"]["spacing"], name="transverse_reinforcement.spacing", allowed_units=["cm"])
    require_value_with_unit(
        config["transverse_reinforcement"]["expected_yield_strength"],
        name="transverse_reinforcement.expected_yield_strength",
        allowed_units=["MPa"],
    )
    if not rebar_exists(str(config["transverse_reinforcement"]["bar_mark"])):
        get_rebar_properties(str(config["transverse_reinforcement"]["bar_mark"]))
    require_keys(
        config["welded_wire_mesh"],
        ["include_for_comparison", "default_diameter", "selectable_diameters_mm", "mechanical_properties"],
        context="welded_wire_mesh",
    )
    mesh_diameter = int(config["welded_wire_mesh"]["default_diameter"]["value"])
    if not mesh_diameter_exists(mesh_diameter):
        get_mesh_properties(mesh_diameter)
    for model in config["concrete"].get("models_to_prepare", []):
        if model.get("name") not in AVAILABLE_MODELS:
            raise ValueError(f"Requested model is not available: {model.get('name')}")
    if config["welded_wire_mesh"].get("model_to_prepare", {}).get("name") != "carrillo_2019_welded_wire_mesh":
        raise ValueError("Unsupported welded wire mesh model requested.")


def _value(config_block: dict[str, Any]) -> float:
    """Return numeric value from a YAML `{value, unit}` block."""

    return float(config_block["value"])


def _optional_value(config_block: dict[str, Any] | None) -> float | None:
    """Return a numeric value when a YAML block exists and is not null/auto."""

    if not config_block:
        return None
    value = config_block.get("value")
    if value is None or value == "auto":
        return None
    return float(value)


def _steel_post_yield_modulus(steel: dict[str, Any]) -> float:
    """Return Et from YAML or derive it from Colombian steel mean values."""

    configured = _optional_value(steel["strain_hardening"].get("post_yield_modulus"))
    if configured is not None:
        return configured

    fy = _value(steel["expected_yield_strength"])
    eps_y = _value(steel["yield_strain"])
    f_sh = _value(steel["hardening_start_stress"])
    eps_sh = _value(steel["strain_hardening"]["hardening_start_strain"])
    return (f_sh - fy) / max(eps_sh - eps_y, 1e-9)


def _resolve_source_pdf(config: dict[str, Any]) -> str | None:
    """Resolve the source PDF path, allowing glob fallback for encoded names."""

    source = config.get("source_reference", {})
    pdf_path = Path(str(source.get("pdf", "")))
    if pdf_path.exists():
        return str(pdf_path)
    pattern = source.get("pdf_search_pattern")
    if pattern:
        matches = sorted(Path().glob(str(pattern)))
        if matches:
            return str(matches[0])
    return None


def build_geometry_and_confinement(config: dict[str, Any]) -> tuple[dict[str, object], dict[str, object]]:
    """Build geometry and confinement summaries from YAML."""

    section_config = config["base_section"]
    assumptions = section_config.get("geometry_assumptions", {})
    gross_section = RectangularSection(
        width_cm=_value(section_config["dimensions"]["width"]),
        height_cm=_value(section_config["dimensions"]["height"]),
    )
    longitudinal = RebarLayout(
        bar_count=int(config["longitudinal_reinforcement"]["count"]),
        bar_mark=str(config["longitudinal_reinforcement"]["bar_mark"]),
        layout_description="symmetric perimeter layout",
    )
    transverse = TransverseReinforcement(
        reinforcement_type=str(config["transverse_reinforcement"]["type"]),
        bar_mark=str(config["transverse_reinforcement"]["bar_mark"]),
        spacing_cm=_value(config["transverse_reinforcement"]["spacing"]),
        diameter_mm=_value(config["transverse_reinforcement"]["diameter"]),
        legs_x=int(assumptions.get("transverse_legs_x", 2)),
        legs_y=int(assumptions.get("transverse_legs_y", 2)),
    )
    rc_section = ReinforcedConcreteSection(
        gross_section=gross_section,
        longitudinal_reinforcement=longitudinal,
        transverse_reinforcement=transverse,
        clear_cover_to_tie_cm=_value(section_config["clear_cover_to_tie"]),
    )
    confined_core = derive_confined_core_from_cover(
        gross_width_cm=gross_section.width_cm,
        gross_height_cm=gross_section.height_cm,
        clear_cover_to_tie_cm=rc_section.clear_cover_to_tie_cm,
        tie_bar_diameter_mm=transverse.effective_diameter_mm,
        boundary=str(assumptions.get("confined_core_boundary", "tie_centerline")),
    )
    confinement_geometry = RectangularConfinementGeometry.from_core(
        confined_core,
        transverse,
        longitudinal_steel_area_cm2=longitudinal.total_area_cm2,
        longitudinal_bars_per_side=int(assumptions.get("longitudinal_bars_per_side", 5)),
    )
    confinement = calculate_rectangular_confinement_parameters(
        confinement_geometry,
        transverse_area_x_mm2=transverse.area_x_mm2,
        transverse_area_y_mm2=transverse.area_y_mm2,
        transverse_yield_strength_mpa=_value(config["transverse_reinforcement"]["expected_yield_strength"]),
    )
    geometry_summary = rc_section.as_dict()
    geometry_summary["confined_core"] = confined_core.as_dict()
    geometry_summary["longitudinal_bars_per_side"] = int(assumptions.get("longitudinal_bars_per_side", 5))
    geometry_summary["geometry_assumptions"] = assumptions
    return geometry_summary, confinement.as_dict()


def generate_material_curves(
    config: dict[str, Any],
    confinement_parameters: dict[str, object],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    """Generate concrete, steel and mesh curves."""

    curve_config = config.get("curve_generation", {})
    num_points = int(curve_config.get("num_points", 401))
    concrete = config["concrete"]
    steel = config["longitudinal_reinforcement"]["steel"]
    transverse = config["transverse_reinforcement"]

    fc = _value(concrete["compressive_strength"])
    ec = 4700.0 * fc**0.5
    eps_co = _value(concrete["strain_parameters"]["epsilon_co"])
    eps_cu_unconfined = _value(concrete["strain_parameters"]["epsilon_cu_unconfined"])
    eps_su_tie = _value(transverse.get("ultimate_strain", {"value": 0.10, "unit": "m/m"}))

    from structurelab_pbd_rc.materials.concrete.confinement import ConfinementParameters

    confinement = ConfinementParameters(
        rho_x=float(confinement_parameters["rho_x"]),
        rho_y=float(confinement_parameters["rho_y"]),
        rho_s=float(confinement_parameters["rho_s"]),
        rho_cc=float(confinement_parameters["rho_cc"]),
        ke=float(confinement_parameters["ke"]),
        fl_eff_mpa=float(confinement_parameters["fl_eff_mpa"]),
        transverse_yield_strength_mpa=float(confinement_parameters["transverse_yield_strength_mpa"]),
        clear_tie_spacing_cm=float(confinement_parameters["clear_tie_spacing_cm"]),
        wi_x_cm=float(confinement_parameters["wi_x_cm"]),
        wi_y_cm=float(confinement_parameters["wi_y_cm"]),
        sum_wi2_cm2=float(confinement_parameters["sum_wi2_cm2"]),
        assumptions=list(confinement_parameters["assumptions"]),
    )

    unconfined_model = UnconfinedConcreteModel(
        UnconfinedConcreteParameters(f_c_mpa=fc, epsilon_co=eps_co, epsilon_cu=eps_cu_unconfined, elastic_modulus_mpa=ec)
    )
    mander_classic_model = ManderClassicConcreteModel(
        ManderClassicParameters(
            f_c_mpa=fc,
            elastic_modulus_mpa=ec,
            epsilon_co=eps_co,
            transverse_steel_ultimate_strain=eps_su_tie,
            confinement=confinement,
        )
    )
    mander_adjusted_model = ManderAdjustedConcreteModel(
        ManderAdjustedParameters(
            f_c_mpa=fc,
            elastic_modulus_mpa=ec,
            epsilon_co=eps_co,
            transverse_steel_ultimate_strain=eps_su_tie,
            confinement=confinement,
        )
    )
    mander_classic_curve = mander_classic_model.generate_curve(num_points)
    mander_adjusted_curve = mander_adjusted_model.generate_curve(num_points)
    concrete_curves = {
        "unconfined_concrete": unconfined_model.generate_curve(num_points),
        "mander_classic": mander_classic_curve,
        "mander_adjusted": mander_adjusted_curve,
        "attard_setunge_unconfined": AttardSetungeConcreteModel(
            AttardSetungeParameters(f_c_mpa=fc, elastic_modulus_mpa=ec, epsilon_peak=eps_co, epsilon_u=eps_cu_unconfined)
        ).generate_curve(num_points),
        "attard_setunge_confined": AttardSetungeConcreteModel(
            AttardSetungeParameters(
                f_c_mpa=fc,
                elastic_modulus_mpa=ec,
                epsilon_peak=eps_co,
                epsilon_u=eps_cu_unconfined,
                confined=True,
                confinement_pressure_mpa=confinement.fl_eff_mpa,
            )
        ).generate_curve(num_points),
    }

    fy = _value(steel["expected_yield_strength"])
    es = _value(steel["elastic_modulus"])
    eps_y = _value(steel["yield_strain"])
    eps_su = _value(steel["ultimate_strain"])
    fu = float(steel.get("ultimate_strength", {}).get("value", 1.25 * fy))
    eps_sh = _value(steel["strain_hardening"]["hardening_start_strain"])
    et = _steel_post_yield_modulus(steel)
    p_value = steel["strain_hardening"].get("parameter_p", {}).get("value") or 4.0
    compression_ultimate_strain = _value(steel["compression_buckling"].get("compression_ultimate_strain", {"value": 0.08, "unit": "m/m"}))

    tension_model = ManderSteelTensionModel(
        SteelTensionParameters(
            fy_mpa=fy,
            fu_mpa=fu,
            elastic_modulus_mpa=es,
            epsilon_y=eps_y,
            strain_hardening_modulus_mpa=et,
            epsilon_sh=eps_sh,
            epsilon_su=eps_su,
            parameter_p=float(p_value),
        )
    )
    compression_model = SteelCompressionModel(
        SteelCompressionParameters(
            fy_mpa=fy,
            fu_mpa=fu,
            elastic_modulus_mpa=es,
            epsilon_y=eps_y,
            epsilon_su_compression=compression_ultimate_strain,
            epsilon_sh=eps_sh,
            strain_hardening_modulus_mpa=et,
            parameter_p=float(p_value),
        )
    )
    buckling_model = BucklingSteelCompressionModel(
        BarBucklingParameters(
            transverse_spacing_cm=_value(transverse["spacing"]),
            longitudinal_bar_diameter_mm=_value(config["longitudinal_reinforcement"]["diameter"]),
            fy_mpa=fy,
            elastic_modulus_mpa=es,
            epsilon_y=eps_y,
            degradation_alpha=float(steel["compression_buckling"]["degradation_alpha"]["value"]),
            ultimate_strain=compression_ultimate_strain,
        )
    )
    steel_curves = {
        "steel_tension": tension_model.generate_curve(num_points),
        "steel_compression_no_buckling": compression_model.generate_curve(num_points),
        "steel_compression_with_buckling": buckling_model.generate_curve(num_points),
    }

    mesh_diameter = int(config["welded_wire_mesh"]["default_diameter"]["value"])
    mesh_data = get_mesh_properties(mesh_diameter)
    mesh_model = CarrilloWeldedWireMeshModel(
        WeldedWireMeshParameters(
            diameter_mm=mesh_diameter,
            fy_mpa=float(mesh_data["fy_mpa"]),
            fu_mpa=float(mesh_data["fu_mpa"]),
            epsilon_u=float(mesh_data["epsilon_u"]),
            elastic_modulus_mpa=es,
        )
    )
    mesh_curves = {"welded_wire_mesh": mesh_model.generate_curve(num_points)}
    return concrete_curves, steel_curves, mesh_curves


def build_initial_results(
    config: dict[str, Any],
    output_dirs: dict[str, Path],
    *,
    geometry_summary: dict[str, object],
    confinement_parameters: dict[str, object],
    curves: dict[str, dict[str, object]],
    metrics: list[dict[str, object]],
    generated_files: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    """Build the Taller 1 result dictionary."""

    return {
        "workshop_id": config["workshop_id"],
        "title": config["title"],
        "status": "completed",
        "message": "Configuracion leida, curvas generadas y salidas exportadas.",
        "source_pdf": _resolve_source_pdf(config),
        "inputs_summary": {
            "base_section": config["base_section"],
            "concrete": config["concrete"],
            "longitudinal_reinforcement": config["longitudinal_reinforcement"],
            "transverse_reinforcement": config["transverse_reinforcement"],
            "welded_wire_mesh": config["welded_wire_mesh"],
        },
        "output_directories": output_dirs,
        "assumptions": list(config["base_section"].get("assumptions", []))
        + list(confinement_parameters.get("assumptions", [])),
        "geometry": geometry_summary,
        "confinement_parameters": confinement_parameters,
        "model_parameters": {name: curve.get("parameters", {}) for name, curve in curves.items()},
        "metrics": metrics,
        "generated_files": generated_files,
        "warnings": warnings,
        "pending_implementation": {
            "future_extensions": [
                "TODO: verificar coeficientes completos de Attard-Setunge contra fuente original sin perdida de formato.",
                "TODO: calibrar modelos de acero contra datos experimentales del curso.",
                "TODO: convertir el reporte PDF minimo en memoria de calculo completa.",
            ]
        },
        "computed_results": {
            "confined_core_geometry": geometry_summary["confined_core"],
            "volumetric_reinforcement_ratio": confinement_parameters["rho_s"],
            "confinement_effectiveness_factor": confinement_parameters["ke"],
            "concrete_curves": list(name for name in curves if "concrete" in name or "mander" in name or "attard" in name),
            "steel_curves": [name for name in curves if "steel" in name],
            "mesh_curves": [name for name in curves if "mesh" in name],
            "comparative_metrics": metrics,
            "figures": [path for key, path in generated_files.items() if key.startswith("figure_")],
            "tables": [path for key, path in generated_files.items() if key.startswith("table_")],
            "reports": [path for key, path in generated_files.items() if key.startswith("report_")],
        },
    }


def run(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_root: str | Path = "outputs",
) -> dict[str, Any]:
    """Read Taller 1 configuration and prepare output directories.

    This workflow intentionally does not implement material equations yet.
    Future phases should call material models from `materials/` and reporting
    functions from `reporting/`.
    """

    result = prepare_workshop_from_config(
        config_path,
        output_root=output_root,
        required_keys=REQUIRED_TOP_LEVEL_KEYS,
    )
    validate_workshop_01_config(result["config"])

    config = result["config"]
    output_dirs = result["output_dirs"]
    geometry_summary, confinement_parameters = build_geometry_and_confinement(config)
    concrete_curves, steel_curves, mesh_curves = generate_material_curves(config, confinement_parameters)
    all_curves = {**concrete_curves, **steel_curves, **mesh_curves}
    metrics = calculate_curve_metrics_table(all_curves)

    data_dir = output_dirs["data"]
    tables_dir = output_dirs["tables"]
    figures_dir = output_dirs["figures"]
    reports_dir = output_dirs["reports"]

    generated_paths: dict[str, Path] = {}
    generated_paths["data_concrete_curves"] = write_csv_rows(curve_rows(concrete_curves), data_dir / "concrete_curves.csv")
    generated_paths["data_steel_curves"] = write_csv_rows(curve_rows(steel_curves), data_dir / "steel_curves.csv")
    generated_paths["data_mesh_curves"] = write_csv_rows(curve_rows(mesh_curves), data_dir / "mesh_curves.csv")
    generated_paths["data_curve_metrics"] = write_csv_rows(metrics, data_dir / "curve_metrics.csv")

    material_parameter_rows = build_material_parameter_table(all_curves)
    confinement_rows = [{"parameter": key, "value": value} for key, value in confinement_parameters.items() if not isinstance(value, list)]
    assumption_rows = build_assumptions_table(
        list(config["base_section"].get("assumptions", [])) + list(confinement_parameters.get("assumptions", []))
    )
    generated_paths["table_material_parameters"] = write_xlsx(
        material_parameter_rows,
        tables_dir / "material_parameters.xlsx",
        sheet_name="material_parameters",
    )
    generated_paths["table_confinement_parameters"] = write_xlsx(
        confinement_rows,
        tables_dir / "confinement_parameters.xlsx",
        sheet_name="confinement",
    )
    generated_paths["table_curve_metrics"] = write_xlsx(metrics, tables_dir / "curve_metrics.xlsx", sheet_name="curve_metrics")
    generated_paths["table_assumptions"] = write_xlsx(assumption_rows, tables_dir / "assumptions_table.xlsx", sheet_name="assumptions")

    generated_paths["figure_concrete"] = plot_stress_strain_curves(
        concrete_curves,
        figures_dir / "concrete_models_comparison.png",
        title="Comparacion de modelos de concreto",
        subtitle="Columna 75 x 75 cm | f'c = 28 MPa | compresion positiva",
        xlabel="Deformacion unitaria de compresion, epsilon_c (m/m)",
        ylabel="Esfuerzo de compresion, f_c (MPa)",
    )
    generated_paths["figure_steel_tension"] = plot_stress_strain_curves(
        {"steel_tension": steel_curves["steel_tension"]},
        figures_dir / "steel_tension_comparison.png",
        title="Acero longitudinal en traccion",
        subtitle=f"Barra #7 | fy medio = {config['longitudinal_reinforcement']['steel']['expected_yield_strength']['value']} MPa",
        xlabel="Deformacion unitaria de traccion, epsilon_s (m/m)",
        ylabel="Esfuerzo de traccion, f_s (MPa)",
    )
    generated_paths["figure_steel_buckling"] = plot_stress_strain_curves(
        {
            "steel_compression_no_buckling": steel_curves["steel_compression_no_buckling"],
            "steel_compression_with_buckling": steel_curves["steel_compression_with_buckling"],
        },
        figures_dir / "steel_compression_buckling.png",
        title="Acero longitudinal en compresion",
        subtitle="Comparacion con y sin degradacion por pandeo | flejes #4 @ 10 cm",
        xlabel="Deformacion unitaria de compresion, epsilon_s (m/m)",
        ylabel="Esfuerzo de compresion, f_s (MPa)",
    )
    generated_paths["figure_mesh"] = plot_stress_strain_curves(
        mesh_curves,
        figures_dir / "welded_wire_mesh.png",
        title="Malla electrosoldada",
        subtitle=f"Diametro seleccionado = {config['welded_wire_mesh']['default_diameter']['value']} mm",
        xlabel="Deformacion unitaria de traccion, epsilon_s (m/m)",
        ylabel="Esfuerzo de traccion, f_s (MPa)",
    )
    generated_paths["figure_core_sketch"] = plot_confined_core_sketch(
        geometry_summary,
        figures_dir / "confined_core_sketch.png",
        title="Seccion base del Taller 1",
    )

    warnings = []
    for curve in all_curves.values():
        warnings.extend(str(warning) for warning in curve.get("warnings", []))

    report_lines = [
        "StructureLab_PBD_RC - Taller 1",
        str(config["title"]),
        f"Seccion: {geometry_summary['gross_section']['width_cm']} cm x {geometry_summary['gross_section']['height_cm']} cm",
        f"f'c: {config['concrete']['compressive_strength']['value']} MPa",
        f"Modelos generados: {', '.join(all_curves)}",
        f"Advertencias: {len(warnings)}",
        "Este PDF es un reporte minimo automatico; la memoria completa queda como extension futura.",
    ]
    generated_paths["report_pdf"] = export_report_to_pdf(report_lines, reports_dir / "workshop_01_report.pdf")

    generated_files = {key: str(path) for key, path in generated_paths.items()}
    initial_results = build_initial_results(
        config,
        output_dirs,
        geometry_summary=geometry_summary,
        confinement_parameters=confinement_parameters,
        curves=all_curves,
        metrics=metrics,
        generated_files=generated_files,
        warnings=warnings,
    )
    results_path = workshop_results_json_path(output_dirs)
    generated_files["data_results_json"] = str(results_path)
    initial_results["generated_files"] = generated_files
    write_json_result(initial_results, results_path)

    result["results"] = initial_results
    result["results_path"] = results_path
    result["generated_files"] = generated_files
    result["warnings"] = warnings
    return result


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for Taller 1."""

    parser = argparse.ArgumentParser(description="Prepare Taller 1 material characterization outputs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to the Taller 1 YAML config.")
    parser.add_argument("--output-root", default="outputs", help="Directory where workshop outputs are created.")
    args = parser.parse_args(argv)

    result = run(config_path=args.config, output_root=args.output_root)
    print(f"Prepared {result['workshop_id']} outputs:")
    print(f"  title: {result['config']['title']}")
    print(f"  config: {args.config}")
    for name, path in result["output_dirs"].items():
        print(f"  {name}: {path}")
    print(f"  results_json: {result['results_path']}")
    print("Generated files:")
    for name, path in result["generated_files"].items():
        print(f"  {name}: {path}")
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

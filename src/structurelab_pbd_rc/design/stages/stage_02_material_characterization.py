"""Etapa 2: jointly process independent material-model JSON inputs."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Mapping
from uuid import uuid4

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.design.stages.stage_02_input_config import (
    ANALYSIS_TYPES,
    MATERIALS,
    Stage02ModelInput,
    load_enabled_stage_02_inputs,
)
from structurelab_pbd_rc.io.write_results import (
    write_csv_rows,
    write_json_result,
    write_yaml_result,
)
from structurelab_pbd_rc.mechanics.idealization import (
    BackbonePoint,
    EnergyEquivalentSettings,
    bilinearize_energy_equivalent,
)
from structurelab_pbd_rc.mechanics.materials.confined_concrete.factory import (
    build_confined_concrete_model,
)
from structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic.mander_1988 import (
    Mander1988MonotonicConfinedConcrete,
)
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.factory import (
    build_ductile_steel_model,
)
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019 import (
    RDM2019MonotonicCompressionModel,
)
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.cyclic.menegotto_pinto import (
    MenegottoPinto,
)
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.factory import (
    build_nonductile_steel_model,
)
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.monotonic.modified_ramberg_osgood import (
    ModifiedRambergOsgood,
)
from structurelab_pbd_rc.mechanics.materials.protocols import linear_strain_vector
from structurelab_pbd_rc.reports.export_excel import write_xlsx
from structurelab_pbd_rc.reports.plots import (
    plot_stress_strain_bilinear_idealization,
    plot_uniaxial_response_rows,
)
from structurelab_pbd_rc.reports.stage_02_material_report import (
    write_stage_02_pdf_report,
)


DEFAULT_CONFIG_PATH = Path("configs/stage_02")

MATERIAL_MODEL_BUILDERS = {
    "confined_concrete": build_confined_concrete_model,
    "ductile_reinforcing_steel": build_ductile_steel_model,
    "nonductile_reinforcing_steel": build_nonductile_steel_model,
}
MATERIAL_DISPLAY_NAMES = {
    "confined_concrete": "Concreto confinado",
    "unconfined_concrete": "Concreto no confinado",
    "ductile_reinforcing_steel": "Acero de refuerzo dúctil",
    "nonductile_reinforcing_steel": "Acero de refuerzo no dúctil",
}
ANALYSIS_DISPLAY_NAMES = {
    "monotonic": "Monotónico",
    "cyclic": "Cíclico",
}


def _require_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be an object.")
    return value


def _optional_bool(
    mapping: Mapping[str, Any],
    key: str,
    *,
    default: bool,
    context: str,
) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{context}.{key} must be true or false.")
    return value


def _response_row(
    *,
    case_id: str,
    step: int,
    response: Any,
    model: Any,
    provenance: Mapping[str, str],
) -> dict[str, Any]:
    diagnostics = response.diagnostics
    stress_state = diagnostics.get("stress_state")
    if stress_state is None:
        stress_state = "zero"
        if response.stress_mpa > 0.0:
            stress_state = "tension"
        elif response.stress_mpa < 0.0:
            stress_state = "compression"
    return {
        "case_id": case_id,
        "step": step,
        "strain": response.strain,
        "stress_mpa": response.stress_mpa,
        "tangent_mpa": response.tangent_mpa,
        "branch": response.branch,
        "loading_direction": response.loading_direction,
        "stress_state": stress_state,
        "reversal": response.reversal,
        "in_domain": response.in_domain,
        "failed": response.failed,
        "compression_policy": getattr(model.parameters, "compression_policy", "history_dependent"),
        "ultimate_strain": getattr(
            model.parameters,
            "ultimate_strain",
            getattr(model, "ultimate_strain", ""),
        ),
        "current_R": diagnostics.get("current_R", ""),
        "xi": diagnostics.get("xi", ""),
        "source": provenance["source"],
        "calibration_status": provenance["calibration_status"],
        "source_location": provenance["source_location"],
        "warnings": " | ".join(response.warnings),
    }


def _evaluate_monotonic_case(
    model: ModifiedRambergOsgood,
    case: Mapping[str, Any],
) -> list[Any]:
    generation = _require_mapping(case.get("curve_generation"), context="curve_generation")
    require_keys(generation, ("points",), context="curve_generation")
    points = int(generation["points"])
    if points < 2:
        raise ConfigError("curve_generation.points must be at least 2.")
    include_tension = _optional_bool(
        generation,
        "include_tension",
        default=True,
        context="curve_generation",
    )
    include_compression = _optional_bool(
        generation,
        "include_compression",
        default=True,
        context="curve_generation",
    )
    compression_supported = (
        model.parameters.compression_policy == "symmetric_prebuckling_assumption"
    )
    strains: list[float] = []
    if include_compression and compression_supported:
        assert model.parameters.compression_strain_limit is not None
        strains.extend(
            linear_strain_vector(
                -model.parameters.compression_strain_limit,
                0.0,
                points,
            )
        )
    if include_tension:
        tensile_strains = linear_strain_vector(0.0, model.parameters.ultimate_strain, points)
        strains.extend(tensile_strains[1:] if strains else tensile_strains)
    if not strains:
        raise ConfigError(
            "curve_generation disables every response branch supported by the model."
        )
    return model.evaluate_many(strains)


def _evaluate_cyclic_case(model: MenegottoPinto, case: Mapping[str, Any]) -> list[Any]:
    history = case.get("strain_history")
    if not isinstance(history, list):
        raise ConfigError("strain_history must be a list for cyclic analysis.")
    interpolation = _require_mapping(
        case.get("history_interpolation"),
        context="history_interpolation",
    )
    require_keys(interpolation, ("points_per_segment",), context="history_interpolation")
    points_per_segment = int(interpolation["points_per_segment"])
    if points_per_segment < 2:
        raise ConfigError("history_interpolation.points_per_segment must be at least 2.")
    if len(history) < 2:
        raise ConfigError("strain_history must contain at least 2 points.")
    expanded: list[float] = []
    for start, stop in zip(history, history[1:]):
        segment = linear_strain_vector(float(start), float(stop), points_per_segment)
        expanded.extend(segment if not expanded else segment[1:])
    return model.evaluate_history(expanded)


def _evaluate_rdm_case(
    model: RDM2019MonotonicCompressionModel,
    case: Mapping[str, Any],
) -> list[Any]:
    generation = _require_mapping(case.get("curve_generation"), context="curve_generation")
    require_keys(generation, ("points", "max_strain"), context="curve_generation")
    points = int(generation["points"])
    max_strain = (
        model.parameters.epsilon_su
        if generation["max_strain"] is None
        else float(generation["max_strain"])
    )
    model.generate_curve(num_points=points, max_strain=max_strain)
    include_tension = _optional_bool(
        generation,
        "include_tension",
        default=True,
        context="curve_generation",
    )
    include_compression = _optional_bool(
        generation,
        "include_compression",
        default=True,
        context="curve_generation",
    )
    responses: list[Any] = []
    if include_compression:
        compressive_strains = linear_strain_vector(-max_strain, 0.0, points)
        responses.extend(
            model.signed_compression_response(strain)
            for strain in compressive_strains
        )
    if include_tension:
        tensile_strains = linear_strain_vector(0.0, max_strain, points)
        if responses:
            tensile_strains = tensile_strains[1:]
        responses.extend(model.tension_response(strain) for strain in tensile_strains)
    if not responses:
        raise ConfigError(
            "curve_generation disables every response branch supported by the model."
        )
    return responses


def _evaluate_mander_1988_case(
    model: Mander1988MonotonicConfinedConcrete,
    case: Mapping[str, Any],
) -> list[Any]:
    generation = _require_mapping(
        case.get("curve_generation"),
        context="curve_generation",
    )
    require_keys(generation, ("points", "max_strain"), context="curve_generation")
    points = int(generation["points"])
    if points < 2:
        raise ConfigError("curve_generation.points must be at least 2.")
    max_strain = (
        model.ultimate_strain
        if generation["max_strain"] is None
        else float(generation["max_strain"])
    )
    model.generate_curve(num_points=points, max_strain=max_strain)
    include_tension = _optional_bool(
        generation,
        "include_tension",
        default=True,
        context="curve_generation",
    )
    include_compression = _optional_bool(
        generation,
        "include_compression",
        default=True,
        context="curve_generation",
    )
    responses: list[Any] = []
    if include_tension:
        tensile_strains = linear_strain_vector(
            -model.tensile_ultimate_strain,
            0.0,
            points,
        )
        responses.extend(model.tension_response(strain) for strain in tensile_strains)
    if include_compression:
        compressive_strains = linear_strain_vector(0.0, max_strain, points)
        if responses:
            compressive_strains = compressive_strains[1:]
        responses.extend(model.response(strain) for strain in compressive_strains)
    if not responses:
        raise ConfigError(
            "curve_generation disables both confined-concrete response branches."
        )
    return responses


def _case_summary(case_id: str, model: Any, responses: list[Any]) -> dict[str, Any]:
    stresses = [response.stress_mpa for response in responses]
    strains = [response.strain for response in responses]
    summary = {
        "case_id": case_id,
        "diameter_mm": model.parameters.diameter_mm,
        "point_count": len(responses),
        "strain_min": min(strains),
        "strain_max": max(strains),
        "stress_min_mpa": min(stresses),
        "stress_max_mpa": max(stresses),
        "reversal_count": sum(response.reversal for response in responses),
        "out_of_domain_count": sum(not response.in_domain for response in responses),
        "failed_count": sum(response.failed for response in responses),
        "calibration_status": model.parameters.provenance.calibration_status,
        "response_branches": sorted(
            {
                str(response.diagnostics["stress_state"])
                for response in responses
                if response.diagnostics.get("stress_state") in {"tension", "compression"}
            }
        ),
    }
    if isinstance(model, RDM2019MonotonicCompressionModel):
        controls = model.summary_parameters()
        summary["rdm_base_inputs"] = {
            key: controls[key]
            for key in (
                "fy_mpa",
                "fu_mpa",
                "elastic_modulus_mpa",
                "epsilon_sh",
                "epsilon_su",
                "parameter_p",
                "longitudinal_bar_diameter_mm",
                "tie_bar_diameter_mm",
                "tie_spacing_mm",
                "effective_tie_leg_length_mm",
                "effective_tie_legs",
                "restrained_longitudinal_bars",
                "tie_steel_modulus_MPa",
                "buckling_restraint_case",
            )
        }
        summary["rdm_controls"] = {
            key: controls[key]
            for key in (
                "epsilon_y",
                "tie_area_mm2",
                "longitudinal_bar_inertia_mm4",
                "reduced_flexural_rigidity_N_mm2",
                "effective_restrained_bars",
                "bar_normalized_stiffness_N_per_mm",
                "tie_stiffness_N_per_mm",
                "equivalent_stiffness_ratio",
                "buckling_intervals",
                "unsupported_length_mm",
                "L_over_D",
                "L_over_D_source",
                "rb",
                "rb_min",
                "eps_i_0",
                "eps_i_max",
                "eps_i",
                "f_it_mpa",
                "alpha_1",
                "alpha_2",
                "alpha",
                "f_i_mpa",
                "eps_ii",
                "residual_stress_mpa",
                "buckling_active",
                "loading_type",
                "sign_convention",
            )
        }
    elif isinstance(model, Mander1988MonotonicConfinedConcrete):
        controls = model.summary_parameters()
        summary["mander_1988_controls"] = {
            key: controls[key]
            for key in (
                "section_type",
                "transverse_reinforcement",
                "rho_cc",
                "rho_s",
                "rho_x",
                "rho_y",
                "k_e",
                "f_lx_mpa",
                "f_ly_mpa",
                "f_l_mpa",
                "elastic_modulus_mpa",
                "f_t_mpa",
                "epsilon_t",
                "f_cc_mpa",
                "epsilon_cc",
                "secant_modulus_mpa",
                "r",
                "epsilon_cu",
                "f_cu_mpa",
            )
        }
    return summary


def _report_payload(
    config: Mapping[str, Any],
    case_summaries: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    model = str(config["model"])
    model_metadata: dict[str, Any] = {}
    if model == ModifiedRambergOsgood.model_id:
        equation = (
            "epsilon = sigma/Es + (eps_u - fu/Es) * (sigma/fu)^n, "
            "0 <= sigma <= fu"
        )
        limitations = [
            (
                "El modelo Ramberg-Osgood modificado implementado para malla electrosoldada "
                "representa la respuesta monotonica en traccion. La respuesta monotonica en "
                "compresion no cuenta con una calibracion especifica para malla NTC 5806; por "
                "defecto se considera no soportada. La opcion simetrica, si se activa, constituye "
                "una hipotesis prepandeo y no una validacion experimental."
            ),
            (
                "La fluencia efectiva FEMA no es un input ni un parametro de la ecuacion "
                "Ramberg-Osgood. Se calcula posteriormente mediante una idealizacion bilineal "
                "de energia equivalente."
            ),
        ]
        model_metadata = {
            "idealization": "asce_fema_energy_equivalent_stress_strain",
            "effective_yield_role": "calculated_result_not_material_input",
        }
    elif model == MenegottoPinto.model_id:
        equation = (
            "Steel02/Menegotto-Pinto con R = R0 * "
            "(1 - cR1 * xi / (cR2 + xi)) y reglas explicitas de reversion."
        )
        limitations = [
            (
                "El modelo Menegotto-Pinto representa la respuesta axial ciclica dentro del rango "
                "y protocolo respaldados por la calibracion seleccionada. No representa por si "
                "solo pandeo, degradacion pospandeo, fractura por fatiga de bajo ciclo ni falla "
                "de soldaduras."
            ),
            (
                "La configuracion incluida verifica el algoritmo y no constituye una calibracion "
                "experimental de malla NTC 5806."
            ),
        ]
    elif model == RDM2019MonotonicCompressionModel.model_id:
        equation = (
            "Rectangular-restraint procedure: keq=kt/k, tabulated n, L=n*s and "
            "L/D=(n*s)/D; RDM 2019 Table 2, Eqs. (1)-(8): reference tension "
            "envelope, intermediate point and bilinear postbuckling degradation."
        )
        limitations = [
            (
                "La implementacion RDM 2019 corresponde a una envolvente constitutiva "
                "uniaxial monotonica. No incluye reglas historicas ciclicas."
            ),
            (
                "El calculo interno RDM usa magnitudes positivas de compresion. El CSV y la "
                "figura exportan traccion con signo positivo y compresion con signo negativo; "
                "no constituyen una historia ciclica."
            ),
            (
                "El calculo de n implementado corresponde inicialmente a secciones "
                "rectangulares con refuerzo transversal. Secciones circulares, losas y "
                "otras configuraciones de restriccion requieren estrategias distintas."
            ),
        ]
        model_metadata = {
            "reference": (
                "Akkaya, Y., Guner, S., & Vecchio, F. J. (2019). Constitutive model "
                "for inelastic buckling behavior of reinforcing bars. ACI Structural "
                "Journal, 116(3), 195-204. DOI 10.14359/51711143."
            ),
            "applicability": {
                "fy_mpa": "200 < fy < 900",
                "diameter_mm": "10 < D < 36",
                "fu_over_fy": "< 2",
                "parameter_p": "<= 4",
                "epsilon_su_over_epsilon_y": "> 14",
                "rb": "8 < rb < 56",
                "l_over_d": ">= 5 for buckling activation",
            },
            "buckling_interval_boundary_convention": (
                "A shared keq boundary is assigned to the larger n mode."
            ),
        }
    elif model == Mander1988MonotonicConfinedConcrete.model_id:
        equation = (
            "Mander et al. (1988), Eqs. (3)-(29): "
            "f_c=f_cc*x*r/(r-1+x^r), x=epsilon_c/epsilon_cc; "
            "linear tension segment f_c=Ec*epsilon_c up to "
            "epsilon_t=f_t/Ec; "
            "for rectangular sections f_l=0.5*k_e*(rho_x+rho_y)*fyh. "
            "The adopted ultimate criterion "
            "is epsilon_cu=0.004+1.4*rho_s*fyh*epsilon_su/f_cc."
        )
        limitations = [
            (
                "La implementacion corresponde a la envolvente uniaxial "
                "monotonica con compresion positiva y un segmento elastico "
                "de traccion negativa. No contiene reglas de descarga, recarga "
                "ni degradacion ciclica."
            ),
            (
                "Para secciones rectangulares se usa la presion efectiva escalar "
                "f_l=0.5*k_e*rho_s*fyh, con rho_s=rho_x+rho_y. f_lx y f_ly se "
                "conservan como diagnosticos y William-Warnke no se implementa."
            ),
            (
                "La deformacion epsilon_cu usa la expresion simplificada elegida "
                "para el proyecto; no implementa el balance energetico de las "
                "Ecs. (59)-(64) del articulo."
            ),
        ]
        model_metadata = {
            "reference": (
                "Mander, J. B., Priestley, M. J. N., & Park, R. (1988). "
                "Theoretical Stress-Strain Model for Confined Concrete. "
                "Journal of Structural Engineering, 114(8), 1804-1826."
            ),
            "implemented_sections": [
                "rectangular_hoops_equivalent_scalar_pressure",
                "circular_hoops",
                "circular_spiral",
            ],
            "rectangular_effective_pressure": (
                "f_l = 0.5 * k_e * (rho_x + rho_y) * fyh"
            ),
            "ultimate_strain_criterion": (
                "simplified_user_selected_expression"
            ),
        }
    else:
        raise ConfigError(f"Missing Stage 2 report definition for model {model!r}.")
    return {
        "stage_id": "stage_02",
        "material": config["material"],
        "analysis_type": config["analysis_type"],
        "model": model,
        "units": config["units"],
        "equation": equation,
        "case_summaries": case_summaries,
        "limitations": limitations,
        "model_metadata": model_metadata,
        "warnings": warnings,
    }


def _mro_fema_idealization(
    model: ModifiedRambergOsgood,
    rows: list[dict[str, Any]],
    case: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate effective FEMA yield without treating fy as a material input."""

    config = _require_mapping(case.get("idealization"), context="idealization")
    require_keys(
        config,
        (
            "method",
            "stiffness_fraction",
            "tolerance",
            "search_points",
            "yield_lower_ratio",
            "yield_upper_ratio",
        ),
        context="idealization",
    )
    method = str(config["method"])
    if method != "asce_fema_energy_equivalent_stress_strain":
        raise ConfigError(
            "idealization.method must be "
            "'asce_fema_energy_equivalent_stress_strain'."
        )
    try:
        result = bilinearize_energy_equivalent(
            (
                BackbonePoint(
                    deformation=float(row["strain"]),
                    response=float(row["stress_mpa"]),
                )
                for row in rows
                if float(row["strain"]) >= 0.0
                and float(row["stress_mpa"]) >= 0.0
            ),
            deformation_u=model.parameters.ultimate_strain,
            settings=EnergyEquivalentSettings(
                stiffness_fraction=float(config["stiffness_fraction"]),
                tolerance=float(config["tolerance"]),
                search_points=int(config["search_points"]),
                yield_lower_ratio=float(config["yield_lower_ratio"]),
                yield_upper_ratio=float(config["yield_upper_ratio"]),
            ),
        )
    except ValueError as exc:
        raise ConfigError(f"Invalid Mon_MRO FEMA idealization: {exc}") from exc

    parameters = result["parameters"]
    area = result["area"]
    return {
        "method": method,
        "status": result["status"],
        "settings": result["settings"],
        "parameters": {
            "E_effective": parameters["effective_stiffness"],
            "f_y_effective": parameters["yield_response"],
            "epsilon_y_effective": parameters["yield_deformation"],
            "E_post_yield": parameters["post_yield_stiffness"],
            "alpha": parameters["alpha"],
            "f_u": parameters["ultimate_response"],
            "epsilon_u": parameters["ultimate_deformation"],
            "f_60y": parameters["fraction_response"],
            "epsilon_60y": parameters["fraction_deformation"],
            "relative_error": parameters["relative_error"],
            "absolute_relative_error": parameters["absolute_relative_error"],
            "ductility": parameters["ductility"],
        },
        "area": {
            "actual": area["actual"],
            "bilinear": area["bilinear"],
        },
        "bilinear_curve": [
            {
                "point": point["point"],
                "strain": point["deformation"],
                "stress_mpa": point["response"],
            }
            for point in result["bilinear_curve"]
        ],
    }


def _plot_rows_by_branch(
    *,
    label: str,
    rows: list[dict[str, Any]],
    analysis_type: str,
) -> dict[str, list[dict[str, Any]]]:
    if analysis_type != "monotonic":
        return {label: rows}

    zero_rows = [row for row in rows if row["stress_state"] == "zero"]
    grouped: dict[str, list[dict[str, Any]]] = {}
    compression_rows = [row for row in rows if row["stress_state"] == "compression"]
    tension_rows = [row for row in rows if row["stress_state"] == "tension"]
    if compression_rows:
        grouped[f"{label} | Compresión"] = sorted(
            [*compression_rows, *zero_rows],
            key=lambda row: float(row["strain"]),
        )
    if tension_rows:
        grouped[f"{label} | Tracción"] = sorted(
            [*zero_rows, *tension_rows],
            key=lambda row: float(row["strain"]),
        )
    if not grouped:
        grouped[label] = rows
    return grouped


def _evaluate_case(model: Any, case: Mapping[str, Any]) -> list[Any]:
    if isinstance(model, ModifiedRambergOsgood):
        return _evaluate_monotonic_case(model, case)
    if isinstance(model, MenegottoPinto):
        return _evaluate_cyclic_case(model, case)
    if isinstance(model, RDM2019MonotonicCompressionModel):
        return _evaluate_rdm_case(model, case)
    if isinstance(model, Mander1988MonotonicConfinedConcrete):
        return _evaluate_mander_1988_case(model, case)
    raise ConfigError(f"Unsupported Stage 2 model instance: {type(model).__name__}")


def _calculated_parameters(model: Any) -> dict[str, Any]:
    """Return model-derived values without modifying constitutive equations."""

    parameters = model.parameters
    if isinstance(model, RDM2019MonotonicCompressionModel):
        values = model.summary_parameters()
        values["s_over_db"] = (
            parameters.tie_spacing_mm / parameters.longitudinal_bar_diameter_mm
        )
        return values
    if isinstance(model, Mander1988MonotonicConfinedConcrete):
        return model.summary_parameters()
    if isinstance(model, ModifiedRambergOsgood):
        elastic_ultimate_strain = (
            parameters.ultimate_strength_mpa / parameters.elastic_modulus_mpa
        )
        return {
            "elastic_ultimate_strain": elastic_ultimate_strain,
            "nonlinear_strain_scale": (
                parameters.ultimate_strain - elastic_ultimate_strain
            ),
        }
    if isinstance(model, MenegottoPinto):
        return {
            "yield_strain": parameters.yield_strain,
            "initial_tangent_mpa": parameters.elastic_modulus_mpa,
        }
    return {}


def _notable_points(
    model: Any,
    rows: list[dict[str, Any]],
    idealization: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return model-aware points for a legend-only technical figure."""

    if isinstance(model, RDM2019MonotonicCompressionModel):
        label_templates = {
            "tension_yield": ("Fluencia en tracción", "fy", "εy"),
            "tension_hardening_start": (
                "Inicio del endurecimiento en tracción",
                "fsh",
                "εsh",
            ),
            "tension_ultimate": (
                "Resistencia última en tracción",
                "fsu",
                "εsu",
            ),
            "compression_yield": ("Fluencia en compresión", "-fy", "-εy"),
            "compression_hardening_start": (
                "Inicio del endurecimiento de referencia en compresión",
                "-fsh",
                "-εsh",
            ),
            "compression_intermediate": (
                "Punto intermedio RDM en compresión",
                "-fi",
                "-εi",
            ),
            "compression_second": (
                "Segundo punto RDM en compresión",
                "-0.75fi",
                "-εii",
            ),
            "compression_ultimate": (
                "Respuesta última en compresión",
                "fsc(εsu)",
                "-εsu",
            ),
        }
        points: list[dict[str, Any]] = []
        for point in model.notable_response_points():
            strain = float(point["strain"])
            stress = float(point["stress_mpa"])
            description, stress_symbol, strain_symbol = label_templates[
                str(point["id"])
            ]
            points.append(
                {
                    "id": point["id"],
                    "strain": strain,
                    "stress_mpa": stress,
                    "legend_group": (
                        "Tracción"
                        if str(point["id"]).startswith("tension_")
                        else "Compresión"
                    ),
                    "label": (
                        f"{description} "
                        f"({stress_symbol} = {stress:.3f} [MPa], "
                        f"{strain_symbol} = {strain:.6f} [mm/mm])"
                    ),
                }
            )
        return points

    if isinstance(model, ModifiedRambergOsgood):
        if idealization is None:
            raise ConfigError("Mon_MRO requires its calculated FEMA idealization.")
        parameters = _require_mapping(
            idealization.get("parameters"),
            context="idealization.parameters",
        )
        return [
            {
                "id": "ultimate",
                "strain": float(parameters["epsilon_u"]),
                "stress_mpa": float(parameters["f_u"]),
                "label": (
                    "Resistencia última "
                    f"(fᵤ = {float(parameters['f_u']):.3f} [MPa], "
                    f"εᵤ = {float(parameters['epsilon_u']):.6f} [mm/mm])"
                ),
            },
        ]

    if isinstance(model, Mander1988MonotonicConfinedConcrete):
        values = model.summary_parameters()
        return [
            {
                "strain": -float(values["epsilon_t"]),
                "stress_mpa": -float(values["f_t_mpa"]),
                "label": (
                    "Resistencia última a tracción "
                    f"(-fₜ = {-float(values['f_t_mpa']):.3f} [MPa], "
                    f"-εₜ = {-float(values['epsilon_t']):.6f} [mm/mm])"
                ),
            },
            {
                "strain": float(values["epsilon_cc"]),
                "stress_mpa": float(values["f_cc_mpa"]),
                "label": (
                    "Resistencia máxima confinada "
                    f"(f′cc = {float(values['f_cc_mpa']):.3f} [MPa], "
                    f"εcc = {float(values['epsilon_cc']):.6f} [mm/mm])"
                ),
            },
            {
                "strain": float(values["epsilon_cu"]),
                "stress_mpa": float(values["f_cu_mpa"]),
                "label": (
                    "Deformación última confinada "
                    f"(fcu = {float(values['f_cu_mpa']):.3f} [MPa], "
                    f"εcu = {float(values['epsilon_cu']):.6f} [mm/mm])"
                ),
            },
        ]

    candidates = [
        min(rows, key=lambda row: float(row["stress_mpa"])),
        max(rows, key=lambda row: float(row["stress_mpa"])),
    ]
    points: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()
    for row in candidates:
        strain = float(row["strain"])
        stress = float(row["stress_mpa"])
        key = (strain, stress)
        if key in seen or (strain == 0.0 and stress == 0.0):
            continue
        seen.add(key)
        descriptor = "máximo" if stress >= 0.0 else "mínimo"
        points.append(
            {
                "strain": strain,
                "stress_mpa": stress,
                "label": (
                    f"Esfuerzo {descriptor} "
                    f"(σ = {stress:.3f} [MPa], ε = {strain:.6f} [mm/mm])"
                ),
            }
        )
    return points


def _prepare_model(item: Stage02ModelInput) -> dict[str, Any]:
    resolved = item.resolved_inputs
    try:
        model_builder = MATERIAL_MODEL_BUILDERS[item.material]
    except KeyError as exc:
        available = ", ".join(sorted(MATERIAL_MODEL_BUILDERS))
        raise ConfigError(
            f"Unsupported Stage 2 material {item.material!r}. Available: {available}"
        ) from exc
    model = model_builder(resolved)
    responses = _evaluate_case(model, resolved)
    provenance = model.parameters.provenance.as_dict()
    rows = [
        _response_row(
            case_id=item.case_id,
            step=step,
            response=response,
            model=model,
            provenance=provenance,
        )
        for step, response in enumerate(responses)
    ]
    warnings: list[str] = []
    for response in responses:
        for warning in response.warnings:
            if warning not in warnings:
                warnings.append(warning)
    summary = _case_summary(item.case_id, model, responses)
    idealization = (
        _mro_fema_idealization(model, rows, resolved)
        if isinstance(model, ModifiedRambergOsgood)
        else None
    )
    calculated = _calculated_parameters(model)
    if idealization is not None:
        calculated["fema_bilinear_idealization"] = idealization
    return {
        "input": item,
        "rows": rows,
        "summary": summary,
        "calculated": calculated,
        "idealization": idealization,
        "notable_points": _notable_points(model, rows, idealization),
        "warnings": warnings,
        "technical_report": _report_payload(resolved, [summary], warnings),
    }


def _model_output_dirs(case_root: Path, item: Stage02ModelInput) -> dict[str, Path]:
    model_root = (
        case_root
        / item.material
        / item.analysis_type
        / item.model_id
    )
    paths = {
        "root": model_root,
        "data": model_root / "data",
        "figures": model_root / "figures",
        "reports": model_root / "reports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _replace_stage_directory(staged_root: Path, stage_root: Path) -> None:
    """Replace the generated Stage 2 tree transactionally."""

    backup_root: Path | None = None
    if stage_root.exists():
        backup_root = stage_root.parent / f".bak-stage_02-{uuid4().hex[:8]}"
        stage_root.replace(backup_root)
    try:
        shutil.move(str(staged_root), str(stage_root))
    except Exception:
        if stage_root.exists():
            shutil.rmtree(stage_root)
        if backup_root is not None and backup_root.exists() and not stage_root.exists():
            backup_root.replace(stage_root)
        raise
    if backup_root is not None:
        shutil.rmtree(backup_root)


def _write_prepared_model(
    prepared: Mapping[str, Any],
    *,
    staged_case_root: Path,
    final_case_root: Path,
) -> dict[str, Any]:
    item: Stage02ModelInput = prepared["input"]
    staged_dirs = _model_output_dirs(staged_case_root, item)
    final_model_root = (
        final_case_root
        / item.material
        / item.analysis_type
        / item.model_id
    )
    final_files = {
        "resolved_inputs_json": final_model_root / "data" / "resolved_inputs.json",
        "calculated_parameters_yaml": (
            final_model_root / "data" / "calculated_parameters.yaml"
        ),
        "metrics_yaml": final_model_root / "data" / "metrics.yaml",
        "curve_csv": final_model_root / "data" / "curve.csv",
        "curve_xlsx": final_model_root / "data" / "curve.xlsx",
        "figure_png": final_model_root / "figures" / "response.png",
        "notable_points_figure_png": (
            final_model_root / "figures" / "response_notable_points.png"
        ),
        "report_yaml": final_model_root / "reports" / "model_report.yaml",
        "report_pdf": final_model_root / "reports" / "model_report.pdf",
    }
    if prepared["idealization"] is not None:
        final_files.update(
            {
                "fema_bilinear_csv": (
                    final_model_root / "data" / "fema_bilinear_idealization.csv"
                ),
                "fema_bilinear_xlsx": (
                    final_model_root / "data" / "fema_bilinear_idealization.xlsx"
                ),
                "fema_bilinear_figure_png": (
                    final_model_root
                    / "figures"
                    / "response_fema_bilinear_idealization.png"
                ),
            }
        )
    staged_files = {
        name: staged_dirs[
            "data"
            if name
            in {
                "resolved_inputs_json",
                "calculated_parameters_yaml",
                "metrics_yaml",
                "curve_csv",
                "curve_xlsx",
                "fema_bilinear_csv",
                "fema_bilinear_xlsx",
            }
            else "figures"
            if name
            in {
                "figure_png",
                "notable_points_figure_png",
                "fema_bilinear_figure_png",
            }
            else "reports"
        ]
        / path.name
        for name, path in final_files.items()
    }

    resolved_payload = {
        "stage_id": "stage_02",
        "project_id": item.project_id,
        "case_id": item.case_id,
        "model_id": item.model_id,
        "source_json": item.source_path,
        "raw": item.raw_config,
        "resolved": item.resolved_inputs,
    }
    write_json_result(resolved_payload, staged_files["resolved_inputs_json"])
    write_yaml_result(
        {"calculated_parameters": prepared["calculated"]},
        staged_files["calculated_parameters_yaml"],
    )
    write_yaml_result(
        {"metrics": prepared["summary"]},
        staged_files["metrics_yaml"],
    )
    write_csv_rows(prepared["rows"], staged_files["curve_csv"])
    write_xlsx(prepared["rows"], staged_files["curve_xlsx"], sheet_name="curve")
    if prepared["idealization"] is not None:
        bilinear_rows = prepared["idealization"]["bilinear_curve"]
        write_csv_rows(bilinear_rows, staged_files["fema_bilinear_csv"])
        write_xlsx(
            bilinear_rows,
            staged_files["fema_bilinear_xlsx"],
            sheet_name="fema_bilinear",
        )
    plot_subtitle = (
        f"{ANALYSIS_DISPLAY_NAMES[item.analysis_type]} | "
        f"{MATERIAL_DISPLAY_NAMES[item.material]} | {item.model_id}"
    )
    if item.model_id == RDM2019MonotonicCompressionModel.model_id:
        l_over_d = float(prepared["calculated"]["L_over_D"])
        buckling_state = (
            "Pandeo activo"
            if prepared["calculated"]["buckling_active"]
            else "Pandeo inactivo"
        )
        plot_subtitle += f" | L/D = {l_over_d:.3f} | {buckling_state}"
    plot_uniaxial_response_rows(
        _plot_rows_by_branch(
            label=str(item.resolved_inputs.get("label", item.title)),
            rows=prepared["rows"],
            analysis_type=item.analysis_type,
        ),
        staged_files["figure_png"],
        title=item.title,
        subtitle=plot_subtitle,
    )
    plot_uniaxial_response_rows(
        _plot_rows_by_branch(
            label=str(item.resolved_inputs.get("label", item.title)),
            rows=prepared["rows"],
            analysis_type=item.analysis_type,
        ),
        staged_files["notable_points_figure_png"],
        title=item.title,
        subtitle=f"{plot_subtitle} | Puntos notables",
        notable_points=prepared["notable_points"],
    )
    if prepared["idealization"] is not None:
        plot_stress_strain_bilinear_idealization(
            prepared["rows"],
            prepared["idealization"]["bilinear_curve"],
            staged_files["fema_bilinear_figure_png"],
            title=f"{item.title} - idealización bilineal",
            subtitle=(
                "Curva monotónica e idealización energética ASCE/FEMA | "
                "$f_{y,\\mathrm{ef}}$ es un resultado calculado"
            ),
        )

    report_payload = {
        "stage_id": "stage_02",
        "project_id": item.project_id,
        "case_id": item.case_id,
        "model_id": item.model_id,
        "title": item.title,
        "status": "completed",
        "metadata": {
            "material": item.material,
            "analysis_type": item.analysis_type,
            "model_id": item.model_id,
            "units": item.units,
            "source_json": item.source_path,
            "provenance": item.resolved_inputs.get("provenance", {}),
        },
        "resolved_inputs": item.resolved_inputs,
        "calculated_parameters": prepared["calculated"],
        "notable_points": prepared["notable_points"],
        "metrics": prepared["summary"],
        "technical_basis": prepared["technical_report"],
        "warnings": prepared["warnings"],
        "generated_files": final_files,
    }
    write_yaml_result(report_payload, staged_files["report_yaml"])
    write_stage_02_pdf_report(
        report_payload,
        staged_files["notable_points_figure_png"],
        staged_files["report_pdf"],
    )
    return report_payload


def run(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_root: str | Path = "outputs",
) -> dict[str, Any]:
    """Process all enabled model JSONs and transactionally rebuild Stage 2."""

    model_inputs = load_enabled_stage_02_inputs(config_path)
    prepared_models = [_prepare_model(item) for item in model_inputs]
    project_ids = {
        (item.project_id, item.case_id)
        for item in model_inputs
    }
    if len(project_ids) != 1:
        raise ConfigError(
            "Stage 2 must resolve every model to the single shared project/case."
        )
    project_id, case_id = next(iter(project_ids))

    output_parent = Path(output_root)
    output_parent.mkdir(parents=True, exist_ok=True)
    stage_root = output_parent / "stage_02"
    staged_stage_root = output_parent / f".stage_02-{uuid4().hex[:8]}"
    staged_case_root = staged_stage_root / project_id / case_id
    for material in MATERIALS:
        for analysis_type in ANALYSIS_TYPES:
            (staged_case_root / material / analysis_type).mkdir(
                parents=True,
                exist_ok=True,
            )
    final_case_root = stage_root / project_id / case_id
    reports: list[dict[str, Any]] = []
    generated_files: dict[str, Path] = {}
    aggregate_warnings: list[str] = []
    try:
        for prepared in prepared_models:
            report = _write_prepared_model(
                prepared,
                staged_case_root=staged_case_root,
                final_case_root=final_case_root,
            )
            reports.append(report)
        _replace_stage_directory(staged_stage_root, stage_root)
    except Exception:
        if staged_stage_root.exists():
            shutil.rmtree(staged_stage_root)
        raise

    for report in reports:
        item_key = (
            f"{project_id}/{case_id}/{report['metadata']['material']}/"
            f"{report['metadata']['analysis_type']}/{report['model_id']}"
        )
        for name, path in report["generated_files"].items():
            generated_files[f"{item_key}/{name}"] = path
        for warning in report["warnings"]:
            if warning not in aggregate_warnings:
                aggregate_warnings.append(warning)
    processed_cases = [
        {
            "project_id": project_id,
            "case_id": case_id,
            "case_root": final_case_root,
            "model_count": len(reports),
        }
    ]

    return {
        "stage_id": "stage_02",
        "title": "Stage 2 enabled constitutive model inputs",
        "status": "completed",
        "config": {"title": "Stage 2 enabled constitutive model inputs"},
        "config_path": Path(config_path),
        "output_dirs": {"root": stage_root},
        "results_path": stage_root,
        "generated_files": generated_files,
        "case_summaries": [prepared["summary"] for prepared in prepared_models],
        "cases": processed_cases,
        "model_reports": reports,
        "warnings": aggregate_warnings,
    }

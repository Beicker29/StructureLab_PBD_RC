"""Pure in-memory material evaluation over the unchanged V1 scientific kernels.

The contracts in this module deliberately keep formulation, parameter-set,
material-instance and cyclic history state as separate concepts.  Native V1
units and sign conventions are preserved; this service performs no boundary
conversion and no publication or presentation work.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
from types import MappingProxyType
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
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
    RDM2019SectionModelSet,
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


NATIVE_UNITS = {"length": "mm", "stress": "MPa", "strain": "mm/mm"}
MATERIAL_MODEL_BUILDERS = {
    "confined_concrete": build_confined_concrete_model,
    "ductile_reinforcing_steel": build_ductile_steel_model,
    "nonductile_reinforcing_steel": build_nonductile_steel_model,
}
SUPPORTED_FORMULATIONS = {
    "Mon_Mander1988": ("confined_concrete", "monotonic"),
    "Mon_RDM2019": ("ductile_reinforcing_steel", "monotonic"),
    "Mon_MRO": ("nonductile_reinforcing_steel", "monotonic"),
    "Cyc_MP": ("nonductile_reinforcing_steel", "cyclic"),
}


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(deepcopy(dict(value)))


def _require_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be an object.")
    return value


def _optional_bool(
    mapping: Mapping[str, Any], key: str, *, default: bool, context: str
) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{context}.{key} must be true or false.")
    return value


@dataclass(frozen=True)
class MaterialFormulation:
    """Stable identity of a scientific formulation, independent of parameters."""

    model_id: str
    material: str
    analysis_type: str

    def __post_init__(self) -> None:
        expected = SUPPORTED_FORMULATIONS.get(self.model_id)
        if expected is None:
            raise ConfigError(f"Unsupported material formulation {self.model_id!r}.")
        if (self.material, self.analysis_type) != expected:
            raise ConfigError(
                f"Formulation {self.model_id!r} requires material/analysis {expected!r}."
            )


@dataclass(frozen=True)
class MaterialParameterSet:
    """Named, immutable set of inputs to one formulation."""

    parameter_set_id: str
    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.parameter_set_id.strip():
            raise ConfigError("parameter_set_id must be non-empty.")
        object.__setattr__(self, "values", _frozen_mapping(self.values))


@dataclass(frozen=True)
class MaterialInstance:
    """One material instance tied to a formulation and parameter set."""

    material_instance_id: str
    formulation: MaterialFormulation
    parameter_set: MaterialParameterSet
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.material_instance_id.strip():
            raise ConfigError("material_instance_id must be non-empty.")
        object.__setattr__(self, "provenance", _frozen_mapping(self.provenance))


@dataclass(frozen=True)
class MaterialEvaluationInput:
    """Structured request containing native inputs but no I/O locations."""

    case_id: str
    instance: MaterialInstance
    units: Mapping[str, str]
    evaluation: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ConfigError("case_id must be non-empty.")
        if dict(self.units) != NATIVE_UNITS:
            raise ConfigError(
                f"Material service accepts native units exactly {NATIVE_UNITS!r}; "
                "use V2 boundary conversions outside the scientific service."
            )
        object.__setattr__(self, "units", MappingProxyType(dict(self.units)))
        object.__setattr__(self, "evaluation", _frozen_mapping(self.evaluation))

    @classmethod
    def from_resolved_inputs(
        cls,
        resolved: Mapping[str, Any],
        *,
        parameter_set_id: str,
        material_instance_id: str,
    ) -> "MaterialEvaluationInput":
        """Adapt the already-resolved V1 Stage 02 input without reading a file."""

        required = (
            "case_id",
            "material",
            "analysis_type",
            "model",
            "units",
            "parameters",
            "provenance",
        )
        require_keys(resolved, required, context="material evaluation input")
        formulation = MaterialFormulation(
            model_id=str(resolved["model"]),
            material=str(resolved["material"]),
            analysis_type=str(resolved["analysis_type"]),
        )
        instance = MaterialInstance(
            material_instance_id=material_instance_id,
            formulation=formulation,
            parameter_set=MaterialParameterSet(
                parameter_set_id=parameter_set_id,
                values=_require_mapping(resolved["parameters"], context="parameters"),
            ),
            provenance=_require_mapping(resolved["provenance"], context="provenance"),
        )
        evaluation = {
            key: deepcopy(value)
            for key, value in resolved.items()
            if key not in required
        }
        return cls(
            case_id=str(resolved["case_id"]),
            instance=instance,
            units=_require_mapping(resolved["units"], context="units"),
            evaluation=evaluation,
        )

    def kernel_config(self) -> dict[str, Any]:
        """Build the factory input in memory, preserving the V1 field names."""

        config = deepcopy(dict(self.evaluation))
        config.update(
            {
                "case_id": self.case_id,
                "material": self.instance.formulation.material,
                "analysis_type": self.instance.formulation.analysis_type,
                "model": self.instance.formulation.model_id,
                "units": dict(self.units),
                "parameters": deepcopy(dict(self.instance.parameter_set.values)),
                "provenance": deepcopy(dict(self.instance.provenance)),
            }
        )
        return config


@dataclass(frozen=True)
class MonotonicMaterialEvaluation:
    case_id: str
    instance: MaterialInstance
    curve: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]
    calculated_parameters: Mapping[str, Any]
    notable_points: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    idealization: Mapping[str, Any] | None = None
    evaluation_status: str = "evaluated"

    def __post_init__(self) -> None:
        object.__setattr__(self, "curve", tuple(_frozen_mapping(row) for row in self.curve))
        object.__setattr__(self, "metrics", _frozen_mapping(self.metrics))
        object.__setattr__(
            self, "calculated_parameters", _frozen_mapping(self.calculated_parameters)
        )
        object.__setattr__(
            self,
            "notable_points",
            tuple(_frozen_mapping(point) for point in self.notable_points),
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.idealization is not None:
            object.__setattr__(self, "idealization", _frozen_mapping(self.idealization))


@dataclass(frozen=True)
class CyclicMaterialEvaluation:
    case_id: str
    instance: MaterialInstance
    curve: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]
    calculated_parameters: Mapping[str, Any]
    notable_points: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    final_committed_state: Mapping[str, Any]
    evaluation_status: str = "evaluated"

    def __post_init__(self) -> None:
        object.__setattr__(self, "curve", tuple(_frozen_mapping(row) for row in self.curve))
        object.__setattr__(self, "metrics", _frozen_mapping(self.metrics))
        object.__setattr__(
            self, "calculated_parameters", _frozen_mapping(self.calculated_parameters)
        )
        object.__setattr__(
            self,
            "notable_points",
            tuple(_frozen_mapping(point) for point in self.notable_points),
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(
            self, "final_committed_state", _frozen_mapping(self.final_committed_state)
        )


MaterialEvaluationResult = MonotonicMaterialEvaluation | CyclicMaterialEvaluation


class CyclicMaterialSession:
    """Stateful Cyc_MP session; each session owns an independent kernel instance."""

    def __init__(self, request: MaterialEvaluationInput) -> None:
        if request.instance.formulation.analysis_type != "cyclic":
            raise ConfigError("CyclicMaterialSession requires a cyclic formulation.")
        model = _build_model(request)
        if not isinstance(model, MenegottoPinto):
            raise ConfigError("The registered cyclic formulation is not Cyc_MP.")
        self._model = model

    @property
    def committed_state(self) -> Any:
        return self._model.committed_state

    @property
    def trial_response(self) -> Any:
        return self._model.trial_response

    def set_trial_strain(self, strain: float) -> Any:
        return self._model.set_trial_strain(strain)

    def commit_state(self) -> None:
        self._model.commit_state()

    def revert_to_last_commit(self) -> Any:
        return self._model.revert_to_last_commit()

    def reset(self) -> Any:
        return self._model.reset()


def create_cyclic_session(request: MaterialEvaluationInput) -> CyclicMaterialSession:
    return CyclicMaterialSession(request)


class MaterialEvaluationService:
    """Stateless application facade over the material evaluation functions.

    The facade gives workflow handlers an injectable service boundary without
    moving state into the service or duplicating any constitutive calculation.
    """

    def evaluate(self, request: MaterialEvaluationInput) -> MaterialEvaluationResult:
        return evaluate_material(request)

    def create_cyclic_session(
        self,
        request: MaterialEvaluationInput,
    ) -> CyclicMaterialSession:
        return create_cyclic_session(request)


def _build_model(request: MaterialEvaluationInput) -> Any:
    formulation = request.instance.formulation
    try:
        builder = MATERIAL_MODEL_BUILDERS[formulation.material]
    except KeyError as exc:
        raise ConfigError(f"Unsupported material {formulation.material!r}.") from exc
    model = builder(request.kernel_config())
    if getattr(model, "model_id", None) != formulation.model_id:
        raise ConfigError("Material factory returned a different formulation.")
    return model


def _evaluate_mro(model: ModifiedRambergOsgood, config: Mapping[str, Any]) -> list[Any]:
    generation = _require_mapping(config.get("curve_generation"), context="curve_generation")
    require_keys(generation, ("points",), context="curve_generation")
    points = int(generation["points"])
    if points < 2:
        raise ConfigError("curve_generation.points must be at least 2.")
    include_tension = _optional_bool(generation, "include_tension", default=True, context="curve_generation")
    include_compression = _optional_bool(generation, "include_compression", default=True, context="curve_generation")
    strains: list[float] = []
    if include_compression and model.parameters.compression_policy == "symmetric_prebuckling_assumption":
        assert model.parameters.compression_strain_limit is not None
        strains.extend(linear_strain_vector(-model.parameters.compression_strain_limit, 0.0, points))
    if include_tension:
        tension = linear_strain_vector(0.0, model.parameters.ultimate_strain, points)
        strains.extend(tension[1:] if strains else tension)
    if not strains:
        raise ConfigError("curve_generation disables every response branch supported by the model.")
    return model.evaluate_many(strains)


def _evaluate_cyclic(model: MenegottoPinto, config: Mapping[str, Any]) -> list[Any]:
    history = config.get("strain_history")
    if not isinstance(history, list):
        raise ConfigError("strain_history must be a list for cyclic analysis.")
    interpolation = _require_mapping(config.get("history_interpolation"), context="history_interpolation")
    require_keys(interpolation, ("points_per_segment",), context="history_interpolation")
    count = int(interpolation["points_per_segment"])
    if count < 2:
        raise ConfigError("history_interpolation.points_per_segment must be at least 2.")
    if len(history) < 2:
        raise ConfigError("strain_history must contain at least 2 points.")
    expanded: list[float] = []
    for start, stop in zip(history, history[1:]):
        segment = linear_strain_vector(float(start), float(stop), count)
        expanded.extend(segment if not expanded else segment[1:])
    return model.evaluate_history(expanded)


def _evaluate_rdm(model: Any, config: Mapping[str, Any]) -> list[Any]:
    generation = _require_mapping(config.get("curve_generation"), context="curve_generation")
    require_keys(generation, ("points", "max_strain"), context="curve_generation")
    points = int(generation["points"])
    if points < 2:
        raise ConfigError("curve_generation.points must be at least 2.")
    reference = model.reference_model if isinstance(model, RDM2019SectionModelSet) else model
    max_strain = reference.parameters.epsilon_su if generation["max_strain"] is None else float(generation["max_strain"])
    include_tension = _optional_bool(generation, "include_tension", default=True, context="curve_generation")
    include_compression = _optional_bool(generation, "include_compression", default=True, context="curve_generation")
    responses: list[Any] = []
    if include_compression:
        models = model.models.values() if isinstance(model, RDM2019SectionModelSet) else (model,)
        for case_model in models:
            case_model.generate_curve(num_points=points, max_strain=max_strain)
            responses.extend(
                case_model.signed_compression_response(strain)
                for strain in linear_strain_vector(-max_strain, 0.0, points)
            )
    if include_tension:
        tension = linear_strain_vector(0.0, max_strain, points)
        if responses and not isinstance(model, RDM2019SectionModelSet):
            tension = tension[1:]
        responses.extend(reference.tension_response(strain) for strain in tension)
    if not responses:
        raise ConfigError("curve_generation disables every response branch supported by the model.")
    return responses


def _evaluate_mander(model: Mander1988MonotonicConfinedConcrete, config: Mapping[str, Any]) -> list[Any]:
    generation = _require_mapping(config.get("curve_generation"), context="curve_generation")
    require_keys(generation, ("points", "max_strain"), context="curve_generation")
    points = int(generation["points"])
    if points < 2:
        raise ConfigError("curve_generation.points must be at least 2.")
    max_strain = model.ultimate_strain if generation["max_strain"] is None else float(generation["max_strain"])
    model.generate_curve(num_points=points, max_strain=max_strain)
    responses: list[Any] = []
    if _optional_bool(generation, "include_tension", default=True, context="curve_generation"):
        responses.extend(
            model.tension_response(strain)
            for strain in linear_strain_vector(-model.tensile_ultimate_strain, 0.0, points)
        )
    if _optional_bool(generation, "include_compression", default=True, context="curve_generation"):
        compression = linear_strain_vector(0.0, max_strain, points)
        if responses:
            compression = compression[1:]
        responses.extend(model.response(strain) for strain in compression)
    if not responses:
        raise ConfigError("curve_generation disables both confined-concrete response branches.")
    return responses


def _evaluate_responses(model: Any, config: Mapping[str, Any]) -> list[Any]:
    if isinstance(model, ModifiedRambergOsgood):
        return _evaluate_mro(model, config)
    if isinstance(model, MenegottoPinto):
        return _evaluate_cyclic(model, config)
    if isinstance(model, (RDM2019SectionModelSet, RDM2019MonotonicCompressionModel)):
        return _evaluate_rdm(model, config)
    if isinstance(model, Mander1988MonotonicConfinedConcrete):
        return _evaluate_mander(model, config)
    raise ConfigError(f"Unsupported material model instance: {type(model).__name__}.")


def _response_row(case_id: str, step: int, response: Any, model: Any) -> dict[str, Any]:
    provenance = model.parameters.provenance.as_dict()
    diagnostics = response.diagnostics
    stress_state = diagnostics.get("stress_state")
    if stress_state is None:
        stress_state = "zero" if response.stress_mpa == 0.0 else ("tension" if response.stress_mpa > 0.0 else "compression")
    return {
        "case_id": case_id,
        "step": step,
        "strain": response.strain,
        "stress_mpa": response.stress_mpa,
        "tangent_mpa": response.tangent_mpa,
        "branch": response.branch,
        "loading_direction": response.loading_direction,
        "stress_state": stress_state,
        "buckling_restraint_case": diagnostics.get("buckling_restraint_case", ""),
        "reversal": response.reversal,
        "in_domain": response.in_domain,
        "failed": response.failed,
        "compression_policy": getattr(model.parameters, "compression_policy", "history_dependent"),
        "ultimate_strain": getattr(model.parameters, "ultimate_strain", getattr(model, "ultimate_strain", "")),
        "current_R": diagnostics.get("current_R", ""),
        "xi": diagnostics.get("xi", ""),
        "source": provenance["source"],
        "calibration_status": provenance["calibration_status"],
        "source_location": provenance["source_location"],
        "warnings": " | ".join(response.warnings),
    }


def _summary(case_id: str, model: Any, responses: list[Any]) -> dict[str, Any]:
    stresses = [response.stress_mpa for response in responses]
    strains = [response.strain for response in responses]
    summary: dict[str, Any] = {
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
    if isinstance(model, RDM2019SectionModelSet):
        controls = model.summary_parameters()
        summary["rdm_material_inputs"] = controls["material"]
        summary["rdm_transverse_reinforcement"] = controls["transverse_reinforcement"]
        keys = (
            "buckling_restraint_case", "effective_tie_leg_length_mm", "effective_tie_legs",
            "restrained_longitudinal_bars", "effective_restrained_bars", "tie_area_mm2",
            "longitudinal_bar_inertia_mm4", "reduced_flexural_rigidity_N_mm2",
            "bar_normalized_stiffness_N_per_mm", "tie_stiffness_N_per_mm",
            "equivalent_stiffness_ratio", "buckling_intervals", "unsupported_length_mm",
            "L_over_D", "rb", "eps_i", "f_i_mpa", "eps_ii",
            "compression_ultimate_stress_mpa", "buckling_active",
        )
        summary["rdm_restraint_cases"] = {
            name: {key: values[key] for key in keys}
            for name, values in controls["restraint_cases"].items()
        }
    elif isinstance(model, RDM2019MonotonicCompressionModel):
        controls = model.summary_parameters()
        base_keys = (
            "fy_mpa", "fu_mpa", "elastic_modulus_mpa", "epsilon_y", "epsilon_sh",
            "epsilon_su", "parameter_p", "longitudinal_bar_diameter_mm",
            "tie_bar_diameter_mm", "tie_spacing_mm", "effective_tie_leg_length_mm",
            "effective_tie_legs", "restrained_longitudinal_bars", "tie_steel_modulus_MPa",
            "buckling_restraint_case",
        )
        control_keys = (
            "epsilon_y", "fu_over_fy", "epsilon_sh_over_epsilon_y",
            "epsilon_su_over_epsilon_y", "tie_area_mm2", "longitudinal_bar_inertia_mm4",
            "reduced_flexural_rigidity_N_mm2", "effective_restrained_bars",
            "bar_normalized_stiffness_N_per_mm", "tie_stiffness_N_per_mm",
            "equivalent_stiffness_ratio", "buckling_intervals", "unsupported_length_mm",
            "L_over_D", "L_over_D_source", "rb", "rb_min", "eps_i_0", "eps_i_max",
            "eps_i", "eps_i_over_epsilon_y", "f_it_mpa", "alpha_1", "alpha_2", "alpha",
            "f_i_mpa", "f_i_over_fy", "eps_ii", "eps_ii_over_epsilon_y",
            "compression_ultimate_stress_mpa", "compression_ultimate_over_fy",
            "residual_stress_mpa", "buckling_active", "loading_type", "sign_convention",
        )
        summary["rdm_base_inputs"] = {key: controls[key] for key in base_keys}
        summary["rdm_controls"] = {key: controls[key] for key in control_keys}
    elif isinstance(model, Mander1988MonotonicConfinedConcrete):
        controls = model.summary_parameters()
        keys = (
            "section_type", "transverse_reinforcement", "rho_cc", "rho_s", "rho_x", "rho_y",
            "k_e", "f_lx_mpa", "f_ly_mpa", "f_l_mpa", "elastic_modulus_mpa", "f_t_mpa",
            "epsilon_t", "f_cc_mpa", "epsilon_cc", "secant_modulus_mpa", "r",
            "epsilon_cu", "f_cu_mpa",
        )
        summary["mander_1988_controls"] = {key: controls[key] for key in keys}
    return summary


def _calculated_parameters(model: Any) -> dict[str, Any]:
    if isinstance(model, (RDM2019SectionModelSet, RDM2019MonotonicCompressionModel, Mander1988MonotonicConfinedConcrete)):
        return model.summary_parameters()
    parameters = model.parameters
    if isinstance(model, ModifiedRambergOsgood):
        elastic_ultimate_strain = parameters.ultimate_strength_mpa / parameters.elastic_modulus_mpa
        return {
            "elastic_ultimate_strain": elastic_ultimate_strain,
            "nonlinear_strain_scale": parameters.ultimate_strain - elastic_ultimate_strain,
        }
    if isinstance(model, MenegottoPinto):
        return {
            "yield_strain": parameters.yield_strain,
            "initial_tangent_mpa": parameters.elastic_modulus_mpa,
        }
    return {}


def _mro_idealization(model: ModifiedRambergOsgood, rows: list[dict[str, Any]], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = _require_mapping(config.get("idealization"), context="idealization")
    require_keys(
        settings,
        ("method", "stiffness_fraction", "tolerance", "search_points", "yield_lower_ratio", "yield_upper_ratio"),
        context="idealization",
    )
    method = str(settings["method"])
    if method != "asce_fema_energy_equivalent_stress_strain":
        raise ConfigError("idealization.method must be 'asce_fema_energy_equivalent_stress_strain'.")
    try:
        result = bilinearize_energy_equivalent(
            (
                BackbonePoint(deformation=float(row["strain"]), response=float(row["stress_mpa"]))
                for row in rows
                if float(row["strain"]) >= 0.0 and float(row["stress_mpa"]) >= 0.0
            ),
            deformation_u=model.parameters.ultimate_strain,
            settings=EnergyEquivalentSettings(
                stiffness_fraction=float(settings["stiffness_fraction"]),
                tolerance=float(settings["tolerance"]),
                search_points=int(settings["search_points"]),
                yield_lower_ratio=float(settings["yield_lower_ratio"]),
                yield_upper_ratio=float(settings["yield_upper_ratio"]),
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
        "area": {"actual": area["actual"], "bilinear": area["bilinear"]},
        "bilinear_curve": [
            {"point": point["point"], "strain": point["deformation"], "stress_mpa": point["response"]}
            for point in result["bilinear_curve"]
        ],
    }


def _notable_points(model: Any, rows: list[dict[str, Any]], idealization: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if isinstance(model, RDM2019SectionModelSet):
        reference = {str(point["id"]): point for point in model.reference_model.notable_response_points()}
        templates = {
            "tension_yield": ("Fluencia en tracción", "fy", "εy", "Tracción"),
            "tension_hardening_start": ("Inicio del endurecimiento en tracción", "fy", "εsh", "Tracción"),
            "tension_ultimate": ("Resistencia última en tracción", "fu", "εu", "Tracción"),
            "compression_yield": ("Fluencia común en compresión", "-fy", "-εy", "Compresión"),
        }
        points: list[dict[str, Any]] = []
        for point_id, (description, stress_symbol, strain_symbol, group) in templates.items():
            point = reference[point_id]
            strain, stress = float(point["strain"]), float(point["stress_mpa"])
            points.append({
                "id": point_id, "strain": strain, "stress_mpa": stress, "legend_group": group,
                "label": f"{description} ({stress_symbol} = {stress:.3f} [MPa], {strain_symbol} = {strain:.6f} [mm/mm])",
            })
        case_labels = {"bending": "Flexión", "pure_compression": "Compresión axial"}
        compression_templates = {
            "compression_intermediate": ("Punto intermedio RDM", "-fi", "-εi"),
            "compression_second": ("Segundo punto RDM", "-0.75fi", "-εii"),
            "compression_ultimate": ("Respuesta última RDM", "-fsc(εu)", "-εu"),
        }
        for case_name, case_model in model.models.items():
            for point in case_model.notable_response_points():
                point_id = str(point["id"])
                if point_id not in compression_templates:
                    continue
                strain, stress = float(point["strain"]), float(point["stress_mpa"])
                description, stress_symbol, strain_symbol = compression_templates[point_id]
                points.append({
                    "id": f"{case_name}_{point_id}", "strain": strain, "stress_mpa": stress,
                    "legend_group": "Compresión",
                    "label": f"{case_labels[case_name]} | {description} ({stress_symbol} = {stress:.3f} [MPa], {strain_symbol} = {strain:.6f} [mm/mm])",
                })
        return points
    if isinstance(model, RDM2019MonotonicCompressionModel):
        templates = {
            "tension_yield": ("Fluencia en tracción", "fy", "εy"),
            "tension_hardening_start": (
                "Inicio del endurecimiento en tracción",
                "fsh",
                "εsh",
            ),
            "tension_ultimate": ("Resistencia última en tracción", "fsu", "εsu"),
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
        points = []
        for point in model.notable_response_points():
            point_id = str(point["id"])
            strain, stress = float(point["strain"]), float(point["stress_mpa"])
            description, stress_symbol, strain_symbol = templates[point_id]
            points.append(
                {
                    "id": point_id,
                    "strain": strain,
                    "stress_mpa": stress,
                    "legend_group": (
                        "Tracción" if point_id.startswith("tension_") else "Compresión"
                    ),
                    "label": (
                        f"{description} ({stress_symbol} = {stress:.3f} [MPa], "
                        f"{strain_symbol} = {strain:.6f} [mm/mm])"
                    ),
                }
            )
        return points
    if isinstance(model, ModifiedRambergOsgood):
        assert idealization is not None
        parameters = _require_mapping(idealization.get("parameters"), context="idealization.parameters")
        strain, stress = float(parameters["epsilon_u"]), float(parameters["f_u"])
        return [{"id": "ultimate", "strain": strain, "stress_mpa": stress, "label": f"Resistencia última (fᵤ = {stress:.3f} [MPa], εᵤ = {strain:.6f} [mm/mm])"}]
    if isinstance(model, Mander1988MonotonicConfinedConcrete):
        values = model.summary_parameters()
        return [
            {"strain": -float(values["epsilon_t"]), "stress_mpa": -float(values["f_t_mpa"]), "label": f"Resistencia última a tracción (-fₜ = {-float(values['f_t_mpa']):.3f} [MPa], -εₜ = {-float(values['epsilon_t']):.6f} [mm/mm])"},
            {"strain": float(values["epsilon_cc"]), "stress_mpa": float(values["f_cc_mpa"]), "label": f"Resistencia máxima confinada (f′cc = {float(values['f_cc_mpa']):.3f} [MPa], εcc = {float(values['epsilon_cc']):.6f} [mm/mm])"},
            {"strain": float(values["epsilon_cu"]), "stress_mpa": float(values["f_cu_mpa"]), "label": f"Deformación última confinada (fcu = {float(values['f_cu_mpa']):.3f} [MPa], εcu = {float(values['epsilon_cu']):.6f} [mm/mm])"},
        ]
    candidates = [min(rows, key=lambda row: float(row["stress_mpa"])), max(rows, key=lambda row: float(row["stress_mpa"]))]
    points: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()
    for row in candidates:
        strain, stress = float(row["strain"]), float(row["stress_mpa"])
        if (strain, stress) in seen or (strain == 0.0 and stress == 0.0):
            continue
        seen.add((strain, stress))
        descriptor = "máximo" if stress >= 0.0 else "mínimo"
        points.append({"strain": strain, "stress_mpa": stress, "label": f"Esfuerzo {descriptor} (σ = {stress:.3f} [MPa], ε = {strain:.6f} [mm/mm])"})
    return points


def evaluate_material(request: MaterialEvaluationInput) -> MaterialEvaluationResult:
    """Evaluate one material entirely in memory using the existing factories."""

    model = _build_model(request)
    config = request.kernel_config()
    responses = _evaluate_responses(model, config)
    rows = [_response_row(request.case_id, step, response, model) for step, response in enumerate(responses)]
    warnings = tuple(dict.fromkeys(warning for response in responses for warning in response.warnings))
    metrics = _summary(request.case_id, model, responses)
    idealization = _mro_idealization(model, rows, config) if isinstance(model, ModifiedRambergOsgood) else None
    calculated = _calculated_parameters(model)
    if idealization is not None:
        calculated["fema_bilinear_idealization"] = idealization
    points = _notable_points(model, rows, idealization)
    common = {
        "case_id": request.case_id,
        "instance": request.instance,
        "curve": tuple(rows),
        "metrics": metrics,
        "calculated_parameters": calculated,
        "notable_points": tuple(points),
        "warnings": warnings,
    }
    if isinstance(model, MenegottoPinto):
        state = model.committed_state
        state_mapping = asdict(state) if is_dataclass(state) else dict(vars(state))
        return CyclicMaterialEvaluation(**common, final_committed_state=state_mapping)
    return MonotonicMaterialEvaluation(**common, idealization=idealization)


__all__ = [
    "CyclicMaterialEvaluation",
    "CyclicMaterialSession",
    "MaterialEvaluationInput",
    "MaterialEvaluationResult",
    "MaterialEvaluationService",
    "MaterialFormulation",
    "MaterialInstance",
    "MaterialParameterSet",
    "MonotonicMaterialEvaluation",
    "NATIVE_UNITS",
    "create_cyclic_session",
    "evaluate_material",
]

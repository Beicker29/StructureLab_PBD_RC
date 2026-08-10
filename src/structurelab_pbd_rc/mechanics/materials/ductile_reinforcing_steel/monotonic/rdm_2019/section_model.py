"""Section-level assembly of RDM 2019 restraint conditions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019.buckling_length import (
    BUCKLING_RESTRAINT_CASES,
)
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019.model import (
    RDM_SPECIAL_HARDENING_EXPONENT,
    RDM2019MonotonicCompressionModel,
    RDM2019Parameters,
)


RESTRAINT_GEOMETRY_KEYS = (
    "effective_tie_leg_length_mm",
    "effective_tie_legs",
    "restrained_longitudinal_bars",
)


@dataclass(frozen=True)
class RDM2019SectionModelSet:
    """RDM envelopes for every documented restraint condition in one section.

    The constitutive equations remain in one model class. This assembly only
    resolves the bending and pure-compression geometries prescribed by User
    Bulletin 3 and creates one model instance per condition.
    """

    models: dict[str, RDM2019MonotonicCompressionModel]

    model_id = RDM2019MonotonicCompressionModel.model_id

    def __post_init__(self) -> None:
        if not self.models:
            raise ConfigError("RDM 2019 requires at least one restraint case.")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "RDM2019SectionModelSet":
        """Build all configured RDM restraint cases from shared physical inputs."""

        require_keys(
            config,
            ("parameters", "provenance"),
            context="RDM 2019 section model",
        )
        raw_parameters = config["parameters"]
        if not isinstance(raw_parameters, Mapping):
            raise ConfigError("parameters must be an object.")
        parameters = deepcopy(dict(raw_parameters))
        restraint_cases = parameters.pop("restraint_cases", None)
        if not isinstance(restraint_cases, Mapping) or not restraint_cases:
            raise ConfigError(
                "parameters.restraint_cases must define bending and "
                "pure_compression geometry."
            )
        missing_cases = set(BUCKLING_RESTRAINT_CASES) - set(restraint_cases)
        if missing_cases:
            names = ", ".join(sorted(missing_cases))
            raise ConfigError(f"Missing documented RDM restraint cases: {names}.")
        forbidden_shared = {
            key
            for key in (*RESTRAINT_GEOMETRY_KEYS, "buckling_restraint_case")
            if key in parameters
        }
        if forbidden_shared:
            names = ", ".join(sorted(forbidden_shared))
            raise ConfigError(
                "RDM restraint-specific values must be inside "
                f"parameters.restraint_cases ({names})."
            )

        models: dict[str, RDM2019MonotonicCompressionModel] = {}
        for raw_name, raw_geometry in restraint_cases.items():
            case_name = str(raw_name).strip()
            if case_name not in BUCKLING_RESTRAINT_CASES:
                available = ", ".join(BUCKLING_RESTRAINT_CASES)
                raise ConfigError(
                    f"Unsupported RDM restraint case {case_name!r}. "
                    f"Available: {available}."
                )
            if case_name in models:
                raise ConfigError(f"Repeated RDM restraint case: {case_name}.")
            if not isinstance(raw_geometry, Mapping):
                raise ConfigError(
                    f"parameters.restraint_cases.{case_name} must be an object."
                )
            geometry = deepcopy(dict(raw_geometry))
            require_keys(
                geometry,
                RESTRAINT_GEOMETRY_KEYS,
                context=f"parameters.restraint_cases.{case_name}",
            )
            unexpected = set(geometry) - set(RESTRAINT_GEOMETRY_KEYS)
            if unexpected:
                names = ", ".join(sorted(unexpected))
                raise ConfigError(
                    f"Unexpected RDM restraint geometry for {case_name}: {names}."
                )
            model_parameters = {
                **parameters,
                **geometry,
                "buckling_restraint_case": case_name,
            }
            model_config = {
                "parameters": model_parameters,
                "provenance": deepcopy(config["provenance"]),
            }
            models[case_name] = RDM2019MonotonicCompressionModel.from_config(
                model_config
            )
        return cls(models=models)

    @property
    def reference_model(self) -> RDM2019MonotonicCompressionModel:
        """Return the model used for the common tensile reference envelope."""

        return self.models.get("bending", next(iter(self.models.values())))

    @property
    def parameters(self) -> RDM2019Parameters:
        """Expose shared parameters for the generic Stage 2 contracts."""

        return self.reference_model.parameters

    def summary_parameters(self) -> dict[str, Any]:
        """Return shared inputs and auditable controls for each restraint case."""

        p = self.parameters
        return {
            "material": {
                "fy_mpa": p.fy_mpa,
                "fu_mpa": p.fu_mpa,
                "epsilon_y": p.epsilon_y,
                "epsilon_sh": p.epsilon_sh,
                "epsilon_su": p.epsilon_su,
                "parameter_p": p.parameter_p,
                "elastic_modulus_mpa": p.elastic_modulus_mpa,
                "special_case_parameter_p": (
                    RDM_SPECIAL_HARDENING_EXPONENT
                ),
            },
            "transverse_reinforcement": {
                "longitudinal_bar_diameter_mm": p.longitudinal_bar_diameter_mm,
                "tie_bar_diameter_mm": p.tie_bar_diameter_mm,
                "tie_spacing_mm": p.tie_spacing_mm,
                "tie_steel_modulus_mpa": p.tie_steel_modulus_mpa,
            },
            "restraint_cases": {
                name: model.summary_parameters()
                for name, model in self.models.items()
            },
            "reference": next(iter(self.models.values())).summary_parameters()[
                "reference"
            ],
            "provenance": p.provenance.as_dict(),
        }

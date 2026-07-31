"""Modified Ramberg-Osgood envelope for nonductile welded-wire reinforcement."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.common import (
    MaterialProvenance,
    UniaxialResponse,
    optional_float,
    required_float,
)


UNSUPPORTED_COMPRESSION = "unsupported"
SYMMETRIC_PREBUCKLING = "symmetric_prebuckling_assumption"


@dataclass(frozen=True)
class ModifiedRambergOsgoodParameters:
    """Physical, numerical and provenance parameters for the monotonic model."""

    elastic_modulus_mpa: float
    ultimate_strength_mpa: float
    ultimate_strain: float
    shape_exponent: float
    provenance: MaterialProvenance
    diameter_mm: float | None = None
    compression_policy: str = UNSUPPORTED_COMPRESSION
    compression_strain_limit: float | None = None
    compression_justification: str | None = None
    compression_explicit_acceptance: bool = False
    root_tolerance: float = 1.0e-12
    max_iterations: int = 200

    def __post_init__(self) -> None:
        if self.elastic_modulus_mpa <= 0.0:
            raise ConfigError("parameters.Es_MPa must be positive.")
        if self.ultimate_strength_mpa <= 0.0:
            raise ConfigError("parameters.fu_MPa must be positive.")
        elastic_ultimate_strain = self.ultimate_strength_mpa / self.elastic_modulus_mpa
        if self.ultimate_strain <= elastic_ultimate_strain:
            raise ConfigError("parameters.eps_u must be greater than fu_MPa / Es_MPa.")
        if self.shape_exponent <= 1.0:
            raise ConfigError("parameters.shape_exponent must be greater than 1.")
        if self.diameter_mm is not None and self.diameter_mm <= 0.0:
            raise ConfigError("parameters.diameter_mm must be positive.")
        if self.root_tolerance <= 0.0:
            raise ConfigError("numerical.root_tolerance must be positive.")
        if self.max_iterations < 1:
            raise ConfigError("numerical.max_iterations must be at least 1.")
        if self.compression_policy not in {UNSUPPORTED_COMPRESSION, SYMMETRIC_PREBUCKLING}:
            raise ConfigError(
                "compression.policy must be 'unsupported' or 'symmetric_prebuckling_assumption'."
            )
        if self.compression_policy == SYMMETRIC_PREBUCKLING:
            if not self.compression_explicit_acceptance:
                raise ConfigError("symmetric compression requires explicit_acceptance: true.")
            if self.compression_strain_limit is None or self.compression_strain_limit <= 0.0:
                raise ConfigError("symmetric compression requires a positive compression_strain_limit.")
            if self.compression_strain_limit > self.ultimate_strain:
                raise ConfigError("compression_strain_limit cannot exceed the tensile eps_u envelope domain.")
            if not self.compression_justification or not self.compression_justification.strip():
                raise ConfigError("symmetric compression requires a non-empty justification.")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ModifiedRambergOsgoodParameters":
        """Build validated parameters from one model case."""

        require_keys(config, ("parameters", "compression", "provenance"), context="monotonic model case")
        parameters = config["parameters"]
        compression = config["compression"]
        provenance = config["provenance"]
        if not isinstance(parameters, Mapping) or not isinstance(compression, Mapping):
            raise ConfigError("parameters and compression must be mappings.")
        if not isinstance(provenance, Mapping):
            raise ConfigError("provenance must be a mapping.")
        forbidden = {"fy_MPa", "yield_definition"}.intersection(parameters)
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise ConfigError(
                f"parameters cannot define {names}; FEMA effective yield is a calculated result."
            )
        require_keys(compression, ("policy",), context="compression")
        numerical = config.get("numerical", {})
        if not isinstance(numerical, Mapping):
            raise ConfigError("numerical must be a mapping.")

        compression_limit = optional_float(
            compression,
            "compression_strain_limit",
            context="compression",
        )
        return cls(
            elastic_modulus_mpa=required_float(parameters, "Es_MPa", context="parameters"),
            ultimate_strength_mpa=required_float(parameters, "fu_MPa", context="parameters"),
            ultimate_strain=required_float(parameters, "eps_u", context="parameters"),
            shape_exponent=required_float(parameters, "shape_exponent", context="parameters"),
            diameter_mm=optional_float(parameters, "diameter_mm", context="parameters"),
            compression_policy=str(compression["policy"]),
            compression_strain_limit=compression_limit,
            compression_justification=(
                None if compression.get("justification") is None else str(compression["justification"])
            ),
            compression_explicit_acceptance=bool(compression.get("explicit_acceptance", False)),
            root_tolerance=float(numerical.get("root_tolerance", 1.0e-12)),
            max_iterations=int(numerical.get("max_iterations", 200)),
            provenance=MaterialProvenance.from_mapping(provenance),
        )


class ModifiedRambergOsgood:
    """Memoryless monotonic tension envelope with explicit compression policy."""

    model_id = "Mon_MRO"

    def __init__(self, parameters: ModifiedRambergOsgoodParameters) -> None:
        self.parameters = parameters

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ModifiedRambergOsgood":
        """Build a model from one case configuration."""

        return cls(ModifiedRambergOsgoodParameters.from_config(config))

    def strain_from_stress(self, stress_mpa: float) -> float:
        """Evaluate the source equation epsilon(sigma) in its tensile domain."""

        p = self.parameters
        stress = float(stress_mpa)
        if stress < 0.0 or stress > p.ultimate_strength_mpa:
            raise MaterialDomainError(
                f"stress must satisfy 0 <= sigma <= fu ({p.ultimate_strength_mpa:g} MPa)."
            )
        nonlinear_scale = p.ultimate_strain - p.ultimate_strength_mpa / p.elastic_modulus_mpa
        return stress / p.elastic_modulus_mpa + nonlinear_scale * (
            stress / p.ultimate_strength_mpa
        ) ** p.shape_exponent

    def tangent_from_stress(self, stress_mpa: float) -> float:
        """Return the analytical tangent d(sigma)/d(epsilon)."""

        p = self.parameters
        stress = float(stress_mpa)
        if stress < 0.0 or stress > p.ultimate_strength_mpa:
            raise MaterialDomainError(
                f"stress must satisfy 0 <= sigma <= fu ({p.ultimate_strength_mpa:g} MPa)."
            )
        nonlinear_scale = p.ultimate_strain - p.ultimate_strength_mpa / p.elastic_modulus_mpa
        derivative = 1.0 / p.elastic_modulus_mpa
        if stress > 0.0:
            derivative += (
                nonlinear_scale
                * p.shape_exponent
                / p.ultimate_strength_mpa
                * (stress / p.ultimate_strength_mpa) ** (p.shape_exponent - 1.0)
            )
        return 1.0 / derivative

    def stress_from_tensile_strain(self, strain: float) -> float:
        """Invert epsilon(sigma) with deterministic bisection over [0, fu]."""

        p = self.parameters
        target = float(strain)
        if target < 0.0 or target > p.ultimate_strain:
            raise MaterialDomainError(
                f"tensile strain must satisfy 0 <= epsilon <= eps_u ({p.ultimate_strain:g})."
            )
        if isclose(target, 0.0, abs_tol=p.root_tolerance):
            return 0.0
        if isclose(target, p.ultimate_strain, abs_tol=p.root_tolerance):
            return p.ultimate_strength_mpa

        lower = 0.0
        upper = p.ultimate_strength_mpa
        lower_residual = self.strain_from_stress(lower) - target
        upper_residual = self.strain_from_stress(upper) - target
        if lower_residual > 0.0 or upper_residual < 0.0:
            raise MaterialDomainError("Ramberg-Osgood inverse root is not bracketed in [0, fu].")

        for _ in range(p.max_iterations):
            midpoint = 0.5 * (lower + upper)
            residual = self.strain_from_stress(midpoint) - target
            if abs(residual) <= p.root_tolerance:
                return midpoint
            if residual < 0.0:
                lower = midpoint
            else:
                upper = midpoint
        raise MaterialDomainError(
            f"Ramberg-Osgood inverse did not converge in {p.max_iterations} iterations."
        )

    def response(self, strain: float) -> UniaxialResponse:
        """Return stress and tangent without extrapolating beyond supported limits."""

        p = self.parameters
        epsilon = float(strain)
        warnings: tuple[str, ...] = ()
        if epsilon < 0.0:
            if p.compression_policy == UNSUPPORTED_COMPRESSION:
                raise MaterialDomainError(
                    "Monotonic compression is unsupported for welded-wire NTC 5806."
                )
            assert p.compression_strain_limit is not None
            if abs(epsilon) > p.compression_strain_limit:
                raise MaterialDomainError(
                    "compressive strain exceeds the explicit symmetric-prebuckling limit."
                )
            tensile_stress = self.stress_from_tensile_strain(abs(epsilon))
            stress = -tensile_stress
            tangent = self.tangent_from_stress(tensile_stress)
            branch = "compression_symmetric_prebuckling_assumption"
            direction = "compression"
            warnings = (
                "Compression is an explicit symmetry assumption, not an NTC 5806 calibration.",
                "Buckling and post-buckling degradation are not represented.",
            )
        else:
            stress = self.stress_from_tensile_strain(epsilon)
            tangent = self.tangent_from_stress(stress)
            branch = "origin" if epsilon == 0.0 else "tension_monotonic"
            direction = "zero" if epsilon == 0.0 else "tension"

        return UniaxialResponse(
            strain=epsilon,
            stress_mpa=stress,
            tangent_mpa=tangent,
            branch=branch,
            loading_direction=direction,
            in_domain=True,
            diagnostics={
                "ultimate_strain": p.ultimate_strain,
                "ultimate_strength_mpa": p.ultimate_strength_mpa,
                "compression_policy": p.compression_policy,
                "source": p.provenance.source,
                "calibration_status": p.provenance.calibration_status,
            },
            warnings=warnings,
        )

    def evaluate_many(self, strains: list[float]) -> list[UniaxialResponse]:
        """Evaluate independent monotonic points in the supplied order."""

        return [self.response(strain) for strain in strains]

"""Mander et al. (1988) monotonic confined-concrete model."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.common import (
    MaterialProvenance,
    UniaxialResponse,
    required_float,
)
from structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic.mander_1988.confinement import (
    ManderConfinementResult,
    calculate_confinement,
)
from structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic.mander_1988.equations import (
    confined_strength_mpa,
    curve_shape_parameter,
    peak_strain,
    popovics_stress_mpa,
    popovics_tangent_mpa,
    secant_modulus_mpa,
    simplified_ultimate_strain,
)
from structurelab_pbd_rc.mechanics.materials.protocols import (
    linear_strain_vector,
)


MANDER_REFERENCE = (
    "Mander, J. B., Priestley, M. J. N., & Park, R. (1988). "
    "Theoretical Stress-Strain Model for Confined Concrete. Journal of "
    "Structural Engineering, 114(8), 1804-1826."
)

@dataclass(frozen=True)
class Mander1988Parameters:
    """Explicit material, geometry and provenance inputs."""

    f_co_mpa: float
    epsilon_co: float
    elastic_modulus_mpa: float
    tensile_strength_mpa: float
    f_yh_mpa: float
    epsilon_su_transverse: float
    geometry: Mapping[str, Any]
    provenance: MaterialProvenance
    confinement: ManderConfinementResult = field(init=False)

    def __post_init__(self) -> None:
        values = (
            self.f_co_mpa,
            self.epsilon_co,
            self.elastic_modulus_mpa,
            self.tensile_strength_mpa,
            self.f_yh_mpa,
            self.epsilon_su_transverse,
        )
        if not all(isfinite(value) for value in values):
            raise ConfigError("Mander 1988 material parameters must be finite.")
        if min(values) <= 0.0:
            raise ConfigError("Mander 1988 material parameters must be positive.")
        confinement = calculate_confinement(
            self.geometry,
            f_yh_mpa=self.f_yh_mpa,
        )
        object.__setattr__(self, "confinement", confinement)

    @property
    def diameter_mm(self) -> float:
        """Return the transverse bar diameter for common Stage 2 metrics."""

        return float(self.geometry["tie_bar_diameter_mm"])

    @property
    def compression_policy(self) -> str:
        """Describe the supported response branch in common Stage 2 rows."""

        return "monotonic_confined_concrete"

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "Mander1988Parameters":
        """Build parameters from one Stage 2 model input."""

        require_keys(
            config,
            ("parameters", "provenance"),
            context="Mander 1988 model case",
        )
        parameters = config["parameters"]
        provenance = config["provenance"]
        if not isinstance(parameters, Mapping):
            raise ConfigError("parameters must be an object.")
        if not isinstance(provenance, Mapping):
            raise ConfigError("provenance must be an object.")
        require_keys(
            parameters,
            (
                "f_co_MPa",
                "epsilon_co",
                "Ec_MPa",
                "f_t_MPa",
                "fyh_MPa",
                "epsilon_su_transverse",
                "geometry",
            ),
            context="parameters",
        )
        geometry = parameters["geometry"]
        if not isinstance(geometry, Mapping):
            raise ConfigError("parameters.geometry must be an object.")
        return cls(
            f_co_mpa=required_float(
                parameters,
                "f_co_MPa",
                context="parameters",
            ),
            epsilon_co=required_float(
                parameters,
                "epsilon_co",
                context="parameters",
            ),
            elastic_modulus_mpa=required_float(
                parameters,
                "Ec_MPa",
                context="parameters",
            ),
            tensile_strength_mpa=required_float(
                parameters,
                "f_t_MPa",
                context="parameters",
            ),
            f_yh_mpa=required_float(
                parameters,
                "fyh_MPa",
                context="parameters",
            ),
            epsilon_su_transverse=required_float(
                parameters,
                "epsilon_su_transverse",
                context="parameters",
            ),
            geometry=dict(geometry),
            provenance=MaterialProvenance.from_mapping(provenance),
        )


class Mander1988MonotonicConfinedConcrete:
    """Stateless monotonic compression envelope for confined concrete."""

    model_id = "Mon_Mander1988"

    def __init__(self, parameters: Mander1988Parameters) -> None:
        self.parameters = parameters
        summary = self._calculate_parameters()
        if summary["elastic_modulus_mpa"] <= summary["secant_modulus_mpa"]:
            raise ConfigError(
                "Mander 1988 requires Ec > Esec so the Popovics parameter r "
                "is finite and positive."
            )
        if summary["epsilon_cu"] <= summary["epsilon_cc"]:
            raise ConfigError(
                "The simplified epsilon_cu criterion must exceed epsilon_cc."
            )
        self._summary = summary

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
    ) -> "Mander1988MonotonicConfinedConcrete":
        return cls(Mander1988Parameters.from_config(config))

    def _calculate_parameters(self) -> dict[str, Any]:
        p = self.parameters
        confinement = p.confinement
        elastic_modulus = p.elastic_modulus_mpa
        f_cc = confined_strength_mpa(p.f_co_mpa, confinement.f_l_mpa)
        epsilon_cc = peak_strain(p.epsilon_co, f_cc, p.f_co_mpa)
        secant_modulus = secant_modulus_mpa(f_cc, epsilon_cc)
        r = curve_shape_parameter(elastic_modulus, secant_modulus)
        epsilon_cu = simplified_ultimate_strain(
            confinement.rho_s,
            p.f_yh_mpa,
            p.epsilon_su_transverse,
            f_cc,
        )
        epsilon_t = p.tensile_strength_mpa / elastic_modulus
        f_cu = popovics_stress_mpa(
            epsilon_cu,
            f_cc_mpa=f_cc,
            epsilon_cc=epsilon_cc,
            r=r,
        )
        return {
            "f_co_mpa": p.f_co_mpa,
            "epsilon_co": p.epsilon_co,
            "elastic_modulus_mpa": elastic_modulus,
            "f_t_mpa": p.tensile_strength_mpa,
            "epsilon_t": epsilon_t,
            "fyh_mpa": p.f_yh_mpa,
            "epsilon_su_transverse": p.epsilon_su_transverse,
            **confinement.as_dict(),
            "f_cc_mpa": f_cc,
            "epsilon_cc": epsilon_cc,
            "secant_modulus_mpa": secant_modulus,
            "r": r,
            "epsilon_cu": epsilon_cu,
            "f_cu_mpa": f_cu,
        }

    @property
    def ultimate_strain(self) -> float:
        return float(self._summary["epsilon_cu"])

    @property
    def peak_confined_strain(self) -> float:
        return float(self._summary["epsilon_cc"])

    @property
    def peak_confined_stress_mpa(self) -> float:
        return float(self._summary["f_cc_mpa"])

    @property
    def tensile_ultimate_strain(self) -> float:
        return float(self._summary["epsilon_t"])

    def stress_at_strain(self, strain: float) -> float:
        """Return positive compression stress for positive strain magnitude."""

        epsilon = float(strain)
        if not isfinite(epsilon):
            raise MaterialDomainError("Mander compressive strain must be finite.")
        if epsilon < 0.0:
            raise MaterialDomainError(
                "Mander compressive strain magnitude cannot be negative."
            )
        if epsilon > self.ultimate_strain:
            return 0.0
        return popovics_stress_mpa(
            epsilon,
            f_cc_mpa=self.peak_confined_stress_mpa,
            epsilon_cc=self.peak_confined_strain,
            r=float(self._summary["r"]),
        )

    def tangent_at_strain(self, strain: float) -> float:
        """Return the analytical tangent of the active monotonic branch."""

        epsilon = float(strain)
        if not isfinite(epsilon):
            raise MaterialDomainError("Mander compressive strain must be finite.")
        if epsilon < 0.0:
            raise MaterialDomainError(
                "Mander compressive strain magnitude cannot be negative."
            )
        if epsilon > self.ultimate_strain:
            return 0.0
        return popovics_tangent_mpa(
            epsilon,
            f_cc_mpa=self.peak_confined_stress_mpa,
            epsilon_cc=self.peak_confined_strain,
            r=float(self._summary["r"]),
        )

    def response(self, strain: float) -> UniaxialResponse:
        """Return one response using positive compression magnitudes."""

        epsilon = float(strain)
        stress = self.stress_at_strain(epsilon)
        if epsilon > self.ultimate_strain:
            branch = "outside_ultimate_domain"
        elif epsilon == 0.0:
            branch = "origin"
        elif epsilon <= self.peak_confined_strain:
            branch = "ascending_confined_compression"
        else:
            branch = "descending_confined_compression"
        return UniaxialResponse(
            strain=epsilon,
            stress_mpa=stress,
            tangent_mpa=self.tangent_at_strain(epsilon),
            branch=branch,
            loading_direction="monotonic_compression_magnitude",
            in_domain=0.0 <= epsilon <= self.ultimate_strain,
            failed=epsilon > self.ultimate_strain,
            diagnostics={
                "stress_state": "compression" if epsilon > 0.0 else "zero",
                "loading_type": "monotonic",
                "sign_convention": "compression_positive",
                "section_type": self.parameters.confinement.section_type,
                "source": self.parameters.provenance.source,
                "calibration_status": (
                    self.parameters.provenance.calibration_status
                ),
            },
        )

    def tension_response(self, strain: float) -> UniaxialResponse:
        """Return the linear tensile segment in the negative quadrant."""

        epsilon = float(strain)
        if not isfinite(epsilon):
            raise MaterialDomainError("Mander tensile strain must be finite.")
        if epsilon > 0.0:
            raise MaterialDomainError(
                "Mander tensile strain cannot be positive."
            )
        if epsilon < -self.tensile_ultimate_strain:
            raise MaterialDomainError(
                "Mander tensile strain cannot exceed the configured epsilon_t."
            )
        stress = self.parameters.elastic_modulus_mpa * epsilon
        return UniaxialResponse(
            strain=epsilon,
            stress_mpa=stress,
            tangent_mpa=self.parameters.elastic_modulus_mpa,
            branch="linear_tension" if epsilon < 0.0 else "origin",
            loading_direction="monotonic_tension",
            in_domain=True,
            failed=False,
            diagnostics={
                "stress_state": "tension" if epsilon < 0.0 else "zero",
                "loading_type": "monotonic",
                "sign_convention": "compression_positive_tension_negative",
                "section_type": self.parameters.confinement.section_type,
                "source": self.parameters.provenance.source,
                "calibration_status": (
                    self.parameters.provenance.calibration_status
                ),
            },
        )

    def signed_compression_response(self, strain: float) -> UniaxialResponse:
        """Return the compression envelope in the physical negative quadrant."""

        epsilon = float(strain)
        if not isfinite(epsilon):
            raise MaterialDomainError("Mander signed strain must be finite.")
        if epsilon > 0.0:
            raise MaterialDomainError(
                "Signed Mander compressive strain cannot be positive."
            )
        magnitude = self.response(abs(epsilon))
        diagnostics = dict(magnitude.diagnostics)
        diagnostics["stress_state"] = "compression" if epsilon < 0.0 else "zero"
        diagnostics["sign_convention"] = (
            "tension_positive_compression_negative"
        )
        return UniaxialResponse(
            strain=epsilon,
            stress_mpa=-magnitude.stress_mpa if epsilon < 0.0 else 0.0,
            tangent_mpa=magnitude.tangent_mpa,
            branch=magnitude.branch,
            loading_direction="monotonic_compression",
            in_domain=magnitude.in_domain,
            failed=magnitude.failed,
            diagnostics=diagnostics,
        )

    def generate_curve(
        self,
        num_points: int = 401,
        max_strain: float | None = None,
    ) -> dict[str, object]:
        """Generate a deterministic compression-positive model curve."""

        if num_points < 2:
            raise ConfigError("num_points must be at least 2.")
        stop = self.ultimate_strain if max_strain is None else float(max_strain)
        if not isfinite(stop) or stop <= 0.0:
            raise ConfigError("max_strain must be finite and positive.")
        if stop > self.ultimate_strain:
            raise ConfigError("max_strain cannot exceed epsilon_cu.")
        strains = linear_strain_vector(0.0, stop, num_points)
        return {
            "strain": strains,
            "stress": [self.stress_at_strain(value) for value in strains],
            "parameters": self.summary_parameters(),
        }

    def summary_parameters(self) -> dict[str, Any]:
        """Expose inputs, calculated controls, equations and provenance."""

        return {
            **self._summary,
            "loading_type": "monotonic",
            "sign_convention": "compression_positive_tension_negative",
            "rectangular_effective_pressure": (
                "f_l = 0.5 * k_e * (rho_x + rho_y) * fyh"
            ),
            "ultimate_strain_criterion": (
                "simplified_user_selected_expression"
            ),
            "equations": {
                "elastic_modulus": "Ec = input",
                "tensile_ultimate_strain": "epsilon_t = f_t / Ec",
                "tensile_segment": "f_c = Ec * epsilon_c, -epsilon_t <= epsilon_c <= 0",
                "effective_lateral_pressure": (
                    "f_l = 0.5 * k_e * rho_s * fyh"
                ),
                "confined_strength": (
                    "f_cc = f_co * (-1.254 + 2.254 * "
                    "sqrt(1 + 7.94*f_l/f_co) - 2*f_l/f_co)"
                ),
                "peak_strain": (
                    "epsilon_cc = epsilon_co * "
                    "(1 + 5*(f_cc/f_co - 1))"
                ),
                "secant_modulus": "Esec = f_cc / epsilon_cc",
                "curve_shape": "r = Ec / (Ec - Esec)",
                "stress": (
                    "f_c = f_cc*x*r / (r - 1 + x^r), "
                    "x = epsilon_c/epsilon_cc"
                ),
                "ultimate_strain": (
                    "epsilon_cu = 0.004 + "
                    "1.4*rho_s*fyh*epsilon_su/f_cc"
                ),
            },
            "reference": MANDER_REFERENCE,
            "provenance": self.parameters.provenance.as_dict(),
        }

"""RDM 2019 monotonic reinforcing-bar compression envelope."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isclose, isfinite, sqrt
from typing import Any, Mapping
from warnings import warn

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.common import (
    MaterialProvenance,
    UniaxialResponse,
    optional_float,
    required_float,
)
from structurelab_pbd_rc.mechanics.materials.protocols import linear_strain_vector
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019.buckling_length import (
    LEGACY_BUCKLING_WARNING,
    UnsupportedBucklingLengthCalculator,
    UnsupportedBucklingLengthResult,
)


RDM_REFERENCE = (
    "Akkaya, Y., Guner, S., & Vecchio, F. J. (2019). Constitutive model for "
    "inelastic buckling behavior of reinforcing bars. ACI Structural Journal, "
    "116(3), 195-204. https://doi.org/10.14359/51711143"
)


@dataclass(frozen=True)
class RDM2019Parameters:
    """Inputs and resolved unsupported-length geometry for RDM 2019."""

    fy_mpa: float
    fu_mpa: float
    elastic_modulus_mpa: float
    epsilon_sh: float
    epsilon_su: float
    longitudinal_bar_diameter_mm: float
    tie_spacing_mm: float
    provenance: MaterialProvenance
    parameter_p: float = 4.0
    tie_bar_diameter_mm: float | None = None
    effective_tie_leg_length_mm: float | None = None
    effective_tie_legs: int | None = None
    restrained_longitudinal_bars: int | None = None
    tie_steel_modulus_mpa: float | None = None
    buckling_restraint_case: str | None = None
    buckling_intervals: int | None = None
    epsilon_y: float | None = None
    _buckling_result: UnsupportedBucklingLengthResult = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        values = (
            self.fy_mpa,
            self.fu_mpa,
            self.elastic_modulus_mpa,
            self.epsilon_sh,
            self.epsilon_su,
            self.longitudinal_bar_diameter_mm,
            self.tie_spacing_mm,
            self.parameter_p,
        )
        if not all(isfinite(value) for value in values):
            raise ConfigError("RDM 2019 parameters must be finite.")
        if self.elastic_modulus_mpa <= 0.0:
            raise ConfigError("parameters.Es_MPa must be positive.")
        if not 0.0 < self.fy_mpa <= self.fu_mpa:
            raise ConfigError("parameters must satisfy 0 < fy_MPa <= fu_MPa.")
        if self.longitudinal_bar_diameter_mm <= 0.0:
            raise ConfigError("parameters.longitudinal_bar_diameter_mm must be positive.")
        if self.parameter_p not in {0.0, 1.0, 4.0}:
            raise ConfigError("parameters.parameter_p must be one of 0, 1 or 4 per RDM Table 2.")
        if self.tie_spacing_mm <= 0.0:
            raise ConfigError("parameters.tie_spacing_mm must be positive.")

        physical_geometry = (
            self.tie_bar_diameter_mm,
            self.effective_tie_leg_length_mm,
            self.effective_tie_legs,
            self.restrained_longitudinal_bars,
            self.tie_steel_modulus_mpa,
            self.buckling_restraint_case,
        )
        has_physical_geometry = any(value is not None for value in physical_geometry)
        has_complete_physical_geometry = all(
            value is not None for value in physical_geometry
        )
        if has_physical_geometry and self.buckling_intervals is not None:
            raise ConfigError(
                "parameters cannot combine buckling_intervals with physical "
                "transverse-restraint variables."
            )
        if has_physical_geometry and self.epsilon_y is not None:
            raise ConfigError(
                "parameters.epsilon_y is derived from fy_MPa / Es_MPa for physical "
                "transverse-restraint inputs."
            )
        if has_physical_geometry and not has_complete_physical_geometry:
            raise ConfigError(
                "Physical RDM restraint geometry requires tie_bar_diameter_mm, "
                "effective_tie_leg_length_mm, effective_tie_legs, "
                "restrained_longitudinal_bars, tie_steel_modulus_MPa and "
                "buckling_restraint_case."
            )

        if has_complete_physical_geometry:
            assert self.tie_bar_diameter_mm is not None
            assert self.effective_tie_leg_length_mm is not None
            assert self.effective_tie_legs is not None
            assert self.restrained_longitudinal_bars is not None
            assert self.tie_steel_modulus_mpa is not None
            assert self.buckling_restraint_case is not None
            buckling_result = UnsupportedBucklingLengthCalculator.calculate(
                fy_mpa=self.fy_mpa,
                elastic_modulus_mpa=self.elastic_modulus_mpa,
                longitudinal_bar_diameter_mm=self.longitudinal_bar_diameter_mm,
                tie_bar_diameter_mm=self.tie_bar_diameter_mm,
                tie_spacing_mm=self.tie_spacing_mm,
                effective_tie_leg_length_mm=self.effective_tie_leg_length_mm,
                effective_tie_legs=self.effective_tie_legs,
                restrained_longitudinal_bars=self.restrained_longitudinal_bars,
                tie_steel_modulus_mpa=self.tie_steel_modulus_mpa,
                buckling_restraint_case=self.buckling_restraint_case,
            )
            object.__setattr__(
                self,
                "effective_tie_legs",
                int(self.effective_tie_legs),
            )
            object.__setattr__(
                self,
                "restrained_longitudinal_bars",
                int(self.restrained_longitudinal_bars),
            )
        else:
            if self.buckling_intervals is None:
                raise ConfigError(
                    "RDM geometry requires complete physical restraint variables. "
                    "Legacy inputs may provide buckling_intervals explicitly."
                )
            warn(LEGACY_BUCKLING_WARNING, DeprecationWarning, stacklevel=2)
            buckling_result = (
                UnsupportedBucklingLengthCalculator.calculate_legacy(
                    fy_mpa=self.fy_mpa,
                    elastic_modulus_mpa=self.elastic_modulus_mpa,
                    longitudinal_bar_diameter_mm=(
                        self.longitudinal_bar_diameter_mm
                    ),
                    tie_spacing_mm=self.tie_spacing_mm,
                    buckling_intervals=self.buckling_intervals,
                )
            )
            if self.epsilon_y is not None and not isclose(
                self.epsilon_y,
                buckling_result.epsilon_y,
                rel_tol=1.0e-9,
                abs_tol=1.0e-12,
            ):
                raise ConfigError(
                    "parameters.epsilon_y must be consistent with fy_MPa / Es_MPa."
                )

        epsilon_y = buckling_result.epsilon_y
        if not 0.0 < epsilon_y < self.epsilon_sh < self.epsilon_su:
            raise ConfigError("parameters must satisfy 0 < epsilon_y < epsilon_sh < epsilon_su.")
        object.__setattr__(self, "epsilon_y", epsilon_y)
        object.__setattr__(
            self,
            "buckling_intervals",
            buckling_result.buckling_intervals,
        )
        object.__setattr__(self, "_buckling_result", buckling_result)

    @property
    def buckling_result(self) -> UnsupportedBucklingLengthResult:
        return self._buckling_result

    @property
    def resolved_l_over_d(self) -> float:
        return self._buckling_result.l_over_d

    @property
    def resolved_unsupported_length_mm(self) -> float:
        return self._buckling_result.unsupported_length_mm

    @property
    def l_over_d_source(self) -> str:
        if self._buckling_result.calculation_mode == "legacy_explicit_buckling_intervals":
            return "legacy input n; L=n*s; L/D=(n*s)/D"
        return "keq=kt/k; tabulated n; L=n*s; L/D=(n*s)/D"

    @property
    def diameter_mm(self) -> float:
        """Common Stage 2 diameter attribute."""

        return self.longitudinal_bar_diameter_mm

    @property
    def ultimate_strain(self) -> float:
        """Common Stage 2 ultimate-strain attribute."""

        return self.epsilon_su

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "RDM2019Parameters":
        """Build parameters from one explicit Stage 2 case."""

        require_keys(
            config,
            ("parameters", "provenance"),
            context="RDM 2019 model case",
        )
        parameters = config["parameters"]
        provenance = config["provenance"]
        if not all(isinstance(item, Mapping) for item in (parameters, provenance)):
            raise ConfigError("parameters and provenance must be objects.")
        forbidden_geometry = {
            key
            for key in (
                "l_over_d",
                "L_over_D",
                "unsupported_length_mm",
                "rb",
                "tie_area_mm2",
                "longitudinal_bar_inertia_mm4",
                "reduced_flexural_rigidity_N_mm2",
                "effective_restrained_bars",
                "bar_normalized_stiffness_N_per_mm",
                "tie_stiffness_N_per_mm",
                "equivalent_stiffness_ratio",
                "buckling_active",
            )
            if key in parameters
        }
        if forbidden_geometry:
            names = ", ".join(sorted(forbidden_geometry))
            raise ConfigError(
                f"RDM geometry cannot receive derived values ({names}); provide "
                "physical transverse-restraint variables."
            )
        for integer_key in (
            "effective_tie_legs",
            "restrained_longitudinal_bars",
            "buckling_intervals",
        ):
            if isinstance(parameters.get(integer_key), bool):
                raise ConfigError(
                    f"parameters.{integer_key} must be a positive integer."
                )
        physical_geometry_keys = (
            "tie_bar_diameter_mm",
            "effective_tie_leg_length_mm",
            "effective_tie_legs",
            "restrained_longitudinal_bars",
            "tie_steel_modulus_MPa",
            "buckling_restraint_case",
        )
        has_physical_geometry = any(
            key in parameters for key in physical_geometry_keys
        )
        if has_physical_geometry:
            require_keys(
                parameters,
                physical_geometry_keys,
                context="parameters",
            )
            conflicting = {
                key
                for key in ("epsilon_y", "buckling_intervals")
                if key in parameters
            }
            if conflicting:
                names = ", ".join(sorted(conflicting))
                raise ConfigError(
                    "Physical RDM restraint inputs cannot be combined with "
                    f"derived or legacy values: {names}."
                )
        elif "buckling_intervals" not in parameters:
            raise ConfigError(
                "parameters requires complete physical transverse-restraint "
                "variables; legacy cases may provide buckling_intervals."
            )
        return cls(
            fy_mpa=required_float(parameters, "fy_MPa", context="parameters"),
            fu_mpa=required_float(parameters, "fu_MPa", context="parameters"),
            elastic_modulus_mpa=required_float(parameters, "Es_MPa", context="parameters"),
            epsilon_y=optional_float(parameters, "epsilon_y", context="parameters"),
            epsilon_sh=required_float(parameters, "epsilon_sh", context="parameters"),
            epsilon_su=required_float(parameters, "epsilon_su", context="parameters"),
            parameter_p=required_float(parameters, "parameter_p", context="parameters"),
            longitudinal_bar_diameter_mm=required_float(
                parameters,
                "longitudinal_bar_diameter_mm",
                context="parameters",
            ),
            tie_spacing_mm=required_float(
                parameters,
                "tie_spacing_mm",
                context="parameters",
            ),
            tie_bar_diameter_mm=optional_float(
                parameters,
                "tie_bar_diameter_mm",
                context="parameters",
            ),
            effective_tie_leg_length_mm=optional_float(
                parameters,
                "effective_tie_leg_length_mm",
                context="parameters",
            ),
            effective_tie_legs=optional_float(
                parameters,
                "effective_tie_legs",
                context="parameters",
            ),
            restrained_longitudinal_bars=optional_float(
                parameters,
                "restrained_longitudinal_bars",
                context="parameters",
            ),
            tie_steel_modulus_mpa=optional_float(
                parameters,
                "tie_steel_modulus_MPa",
                context="parameters",
            ),
            buckling_restraint_case=(
                None
                if "buckling_restraint_case" not in parameters
                else str(parameters["buckling_restraint_case"])
            ),
            buckling_intervals=optional_float(
                parameters,
                "buckling_intervals",
                context="parameters",
            ),
            provenance=MaterialProvenance.from_mapping(provenance),
        )


class RDM2019MonotonicCompressionModel:
    """Stateless RDM 2019 tension reference and compression envelope."""

    model_id = "steel_compression_rdm_2019_monotonic"

    def __init__(self, parameters: RDM2019Parameters) -> None:
        self.parameters = parameters

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "RDM2019MonotonicCompressionModel":
        return cls(RDM2019Parameters.from_config(config))

    @property
    def buckling_active(self) -> bool:
        """RDM activates at the inclusive L/D threshold from Table 2."""

        return self.parameters.buckling_result.buckling_active

    @property
    def rb(self) -> float:
        return self.parameters.buckling_result.rb

    @property
    def rb_min(self) -> float:
        return 5.0 * sqrt(self.parameters.fy_mpa / 100.0)

    @property
    def epsilon_i_0(self) -> float | None:
        if not self.buckling_active:
            return None
        assert self.parameters.epsilon_y is not None
        return self.parameters.epsilon_y * (55.0 - 2.3 * self.rb)

    @property
    def epsilon_i_max(self) -> float | None:
        if not self.buckling_active:
            return None
        assert self.parameters.epsilon_y is not None
        return self.parameters.epsilon_y * (55.0 - 2.3 * self.rb_min)

    @property
    def epsilon_i(self) -> float | None:
        if not self.buckling_active:
            return None
        p = self.parameters
        assert p.epsilon_y is not None
        epsilon_i_0 = self.epsilon_i_0
        epsilon_i_max = self.epsilon_i_max
        assert epsilon_i_0 is not None
        assert epsilon_i_max is not None
        if epsilon_i_0 < p.epsilon_su < epsilon_i_max:
            candidate = epsilon_i_0 * p.epsilon_su / epsilon_i_max
        else:
            candidate = epsilon_i_0
        return max(7.0 * p.epsilon_y, candidate)

    def _reference_tension_stress(self, strain: float, *, exponent: float | None = None) -> float:
        """Evaluate the single Table 2 Eq. (4) tensile reference envelope."""

        p = self.parameters
        assert p.epsilon_y is not None
        epsilon = float(strain)
        if epsilon < 0.0:
            raise MaterialDomainError("RDM strain magnitude cannot be negative.")
        if epsilon <= p.epsilon_y:
            return p.elastic_modulus_mpa * epsilon
        if epsilon <= p.epsilon_sh:
            return p.fy_mpa
        if epsilon < p.epsilon_su:
            power = p.parameter_p if exponent is None else exponent
            ratio = (p.epsilon_su - epsilon) / (p.epsilon_su - p.epsilon_sh)
            return p.fu_mpa + (p.fy_mpa - p.fu_mpa) * ratio**power
        if isclose(epsilon, p.epsilon_su, abs_tol=1.0e-15):
            return p.fu_mpa
        return 0.0

    def _reference_tension_tangent(self, strain: float) -> float:
        p = self.parameters
        assert p.epsilon_y is not None
        if strain <= p.epsilon_y:
            return p.elastic_modulus_mpa
        if strain <= p.epsilon_sh or strain >= p.epsilon_su or p.parameter_p == 0.0:
            return 0.0
        ratio = (p.epsilon_su - strain) / (p.epsilon_su - p.epsilon_sh)
        return (
            (p.fu_mpa - p.fy_mpa)
            * p.parameter_p
            * ratio ** (p.parameter_p - 1.0)
            / (p.epsilon_su - p.epsilon_sh)
        )

    @property
    def uses_special_alpha_case(self) -> bool:
        if not self.buckling_active:
            return False
        p = self.parameters
        assert p.epsilon_y is not None
        epsilon_i = self.epsilon_i
        epsilon_i_max = self.epsilon_i_max
        assert epsilon_i is not None
        assert epsilon_i_max is not None
        return p.epsilon_su <= epsilon_i_max and isclose(
            epsilon_i,
            7.0 * p.epsilon_y,
            rel_tol=1.0e-9,
            abs_tol=1.0e-12,
        )

    @property
    def f_it_mpa(self) -> float | None:
        if not self.buckling_active:
            return None
        epsilon_i = self.epsilon_i
        assert epsilon_i is not None
        exponent = 1.0 if self.uses_special_alpha_case else None
        return self._reference_tension_stress(epsilon_i, exponent=exponent)

    @property
    def alpha_1(self) -> float | None:
        if not self.buckling_active:
            return None
        p = self.parameters
        return 0.8 + 1.8 * (p.fu_mpa / p.fy_mpa) / p.resolved_l_over_d

    @property
    def alpha_2(self) -> float | None:
        if not self.buckling_active:
            return None
        return 1.1 - 0.016 * self.rb

    @property
    def alpha(self) -> float | None:
        if not self.buckling_active:
            return None
        p = self.parameters
        epsilon_i = self.epsilon_i
        f_it = self.f_it_mpa
        alpha_1 = self.alpha_1
        alpha_2 = self.alpha_2
        assert epsilon_i is not None
        assert f_it is not None
        assert alpha_1 is not None
        assert alpha_2 is not None
        if self.uses_special_alpha_case:
            return 0.75 * alpha_2 * (f_it / p.fy_mpa)
        if epsilon_i > p.epsilon_sh:
            return alpha_1 * alpha_2
        return 0.75 * alpha_1 * alpha_2

    @property
    def f_i_mpa(self) -> float | None:
        if not self.buckling_active:
            return None
        p = self.parameters
        alpha = self.alpha
        f_it = self.f_it_mpa
        assert alpha is not None
        assert f_it is not None
        return min(f_it, max(self.residual_stress_mpa, alpha * p.fy_mpa))

    @property
    def epsilon_ii(self) -> float | None:
        if not self.buckling_active:
            return None
        p = self.parameters
        epsilon_i = self.epsilon_i
        f_i = self.f_i_mpa
        assert epsilon_i is not None
        assert f_i is not None
        return epsilon_i + 0.25 * f_i / (0.02 * p.elastic_modulus_mpa)

    @property
    def residual_stress_mpa(self) -> float:
        return 0.2 * self.parameters.fy_mpa

    def applicability_warnings(self) -> tuple[str, ...]:
        """Report deviations from the broad ranges stated by the authors."""

        p = self.parameters
        assert p.epsilon_y is not None
        checks = (
            (p.fu_mpa / p.fy_mpa < 2.0, "fu/fy is outside the reported fu/fy < 2 range."),
            (p.parameter_p <= 4.0, "P is outside the reported P <= 4 range."),
            (
                p.epsilon_su > 14.0 * p.epsilon_y,
                "epsilon_su is outside the reported epsilon_su > 14 epsilon_y range.",
            ),
        )
        warnings = [
            *p.buckling_result.applicability_warnings,
            *(message for valid, message in checks if not valid),
        ]
        return tuple(dict.fromkeys(warnings))

    def stress_at_strain(self, strain: float) -> float:
        """Return positive compressive stress magnitude for positive strain magnitude."""

        p = self.parameters
        assert p.epsilon_y is not None
        epsilon = float(strain)
        if not isfinite(epsilon):
            raise MaterialDomainError("RDM strain magnitude must be finite.")
        if epsilon < 0.0:
            raise MaterialDomainError("RDM strain magnitude cannot be negative.")
        if epsilon > p.epsilon_su:
            return 0.0
        if not self.buckling_active:
            return self._reference_tension_stress(epsilon)
        if epsilon <= p.epsilon_y:
            return p.elastic_modulus_mpa * epsilon

        epsilon_i = self.epsilon_i
        epsilon_ii = self.epsilon_ii
        f_i = self.f_i_mpa
        f_it = self.f_it_mpa
        assert epsilon_i is not None
        assert epsilon_ii is not None
        assert f_i is not None
        assert f_it is not None
        if epsilon <= epsilon_i:
            f_st = self._reference_tension_stress(epsilon)
            transition = (epsilon - p.epsilon_y) / (epsilon_i - p.epsilon_y)
            stress = f_st * (1.0 - (1.0 - f_i / f_it) * transition)
        elif epsilon <= epsilon_ii:
            stress = f_i - 0.02 * p.elastic_modulus_mpa * (epsilon - epsilon_i)
        else:
            stress = 0.75 * f_i - 0.01 * p.elastic_modulus_mpa * (epsilon - epsilon_ii)
        return max(self.residual_stress_mpa, stress)

    def tangent_at_strain(self, strain: float) -> float:
        """Return the analytical tangent of the active monotonic branch."""

        p = self.parameters
        assert p.epsilon_y is not None
        epsilon = float(strain)
        if epsilon < 0.0 or epsilon > p.epsilon_su:
            return 0.0
        if not self.buckling_active:
            return self._reference_tension_tangent(epsilon)
        if epsilon <= p.epsilon_y:
            return p.elastic_modulus_mpa

        epsilon_i = self.epsilon_i
        epsilon_ii = self.epsilon_ii
        f_i = self.f_i_mpa
        f_it = self.f_it_mpa
        assert epsilon_i is not None
        assert epsilon_ii is not None
        assert f_i is not None
        assert f_it is not None
        stress = self.stress_at_strain(epsilon)
        if isclose(stress, self.residual_stress_mpa, abs_tol=1.0e-12):
            return 0.0
        if epsilon <= epsilon_i:
            factor = 1.0 - f_i / f_it
            transition = (epsilon - p.epsilon_y) / (epsilon_i - p.epsilon_y)
            f_st = self._reference_tension_stress(epsilon)
            return (
                self._reference_tension_tangent(epsilon) * (1.0 - factor * transition)
                - f_st * factor / (epsilon_i - p.epsilon_y)
            )
        if epsilon <= epsilon_ii:
            return -0.02 * p.elastic_modulus_mpa
        return -0.01 * p.elastic_modulus_mpa

    def response(self, strain: float) -> UniaxialResponse:
        """Return one stateless response using compression-positive magnitudes."""

        p = self.parameters
        epsilon = float(strain)
        stress = self.stress_at_strain(epsilon)
        if epsilon > p.epsilon_su:
            branch = "outside_ultimate_domain"
        elif not self.buckling_active:
            branch = "reference_envelope_no_buckling"
        elif p.epsilon_y is not None and epsilon <= p.epsilon_y:
            branch = "elastic_compression"
        elif self.epsilon_i is not None and epsilon <= self.epsilon_i:
            branch = "rdm_transition_to_intermediate_point"
        elif self.epsilon_ii is not None and epsilon <= self.epsilon_ii:
            branch = "rdm_postbuckling_first_slope"
        else:
            branch = "rdm_postbuckling_second_slope_or_residual"
        return UniaxialResponse(
            strain=epsilon,
            stress_mpa=stress,
            tangent_mpa=self.tangent_at_strain(epsilon),
            branch=branch,
            loading_direction="monotonic_compression_magnitude",
            in_domain=0.0 <= epsilon <= p.epsilon_su,
            diagnostics={
                "stress_state": "compression" if epsilon > 0.0 else "zero",
                "loading_type": "monotonic",
                "sign_convention": "compression_positive",
                "buckling_active": self.buckling_active,
                "L_over_D": p.resolved_l_over_d,
                "rb": self.rb,
                "epsilon_i": self.epsilon_i,
                "f_i_mpa": self.f_i_mpa,
                "epsilon_ii": self.epsilon_ii,
                "residual_stress_mpa": self.residual_stress_mpa,
                "source": p.provenance.source,
                "calibration_status": p.provenance.calibration_status,
            },
            warnings=self.applicability_warnings(),
        )

    def tension_response(self, strain: float) -> UniaxialResponse:
        """Return the signed monotonic reference-tension response."""

        p = self.parameters
        assert p.epsilon_y is not None
        epsilon = float(strain)
        if not isfinite(epsilon):
            raise MaterialDomainError("RDM tensile strain must be finite.")
        if epsilon < 0.0:
            raise MaterialDomainError("RDM tensile strain cannot be negative.")
        stress = self._reference_tension_stress(epsilon)
        if epsilon > p.epsilon_su:
            branch = "outside_ultimate_domain"
        elif epsilon <= p.epsilon_y:
            branch = "elastic_tension"
        elif epsilon <= p.epsilon_sh:
            branch = "tension_yield_plateau"
        else:
            branch = "tension_strain_hardening"
        return UniaxialResponse(
            strain=epsilon,
            stress_mpa=stress,
            tangent_mpa=self._reference_tension_tangent(epsilon),
            branch=branch,
            loading_direction="monotonic_tension",
            in_domain=0.0 <= epsilon <= p.epsilon_su,
            diagnostics={
                "stress_state": "tension" if epsilon > 0.0 else "zero",
                "loading_type": "monotonic",
                "sign_convention": "tension_positive_compression_negative",
                "source": p.provenance.source,
                "calibration_status": p.provenance.calibration_status,
            },
            warnings=self.applicability_warnings(),
        )

    def signed_compression_response(self, strain: float) -> UniaxialResponse:
        """Return the RDM compression envelope in the negative quadrant."""

        epsilon = float(strain)
        if not isfinite(epsilon):
            raise MaterialDomainError("RDM compressive strain must be finite.")
        if epsilon > 0.0:
            raise MaterialDomainError("Signed RDM compressive strain cannot be positive.")
        magnitude_response = self.response(abs(epsilon))
        diagnostics = dict(magnitude_response.diagnostics)
        diagnostics["stress_state"] = "compression" if epsilon < 0.0 else "zero"
        diagnostics["sign_convention"] = "tension_positive_compression_negative"
        return UniaxialResponse(
            strain=epsilon,
            stress_mpa=-magnitude_response.stress_mpa if epsilon < 0.0 else 0.0,
            tangent_mpa=magnitude_response.tangent_mpa,
            branch=magnitude_response.branch,
            loading_direction="monotonic_compression",
            in_domain=magnitude_response.in_domain,
            failed=magnitude_response.failed,
            diagnostics=diagnostics,
            warnings=magnitude_response.warnings,
        )

    def evaluate_many(self, strains: list[float]) -> list[UniaxialResponse]:
        return [self.response(strain) for strain in strains]

    def summary_parameters(self) -> dict[str, Any]:
        """Expose inputs, derived controls, applicability and provenance."""

        p = self.parameters
        buckling = p.buckling_result.as_dict()
        return {
            "fy_mpa": p.fy_mpa,
            "fu_mpa": p.fu_mpa,
            "elastic_modulus_mpa": p.elastic_modulus_mpa,
            "eps_y": p.epsilon_y,
            "epsilon_y": p.epsilon_y,
            "epsilon_sh": p.epsilon_sh,
            "epsilon_su": p.epsilon_su,
            "parameter_p": p.parameter_p,
            "longitudinal_bar_diameter_mm": p.longitudinal_bar_diameter_mm,
            "tie_bar_diameter_mm": p.tie_bar_diameter_mm,
            "tie_spacing_mm": p.tie_spacing_mm,
            "effective_tie_leg_length_mm": p.effective_tie_leg_length_mm,
            "effective_tie_legs": p.effective_tie_legs,
            "restrained_longitudinal_bars": p.restrained_longitudinal_bars,
            "tie_steel_modulus_MPa": p.tie_steel_modulus_mpa,
            "buckling_restraint_case": buckling["buckling_restraint_case"],
            "s_over_db": p.tie_spacing_mm / p.longitudinal_bar_diameter_mm,
            "L_over_D_source": p.l_over_d_source,
            **buckling,
            "rb_min": self.rb_min,
            "eps_i_0": self.epsilon_i_0,
            "eps_i_max": self.epsilon_i_max,
            "eps_i": self.epsilon_i,
            "f_it_mpa": self.f_it_mpa,
            "alpha_1": self.alpha_1,
            "alpha_2": self.alpha_2,
            "alpha": self.alpha,
            "f_i_mpa": self.f_i_mpa,
            "eps_ii": self.epsilon_ii,
            "residual_stress_mpa": self.residual_stress_mpa,
            "buckling_active": self.buckling_active,
            "special_alpha_case": self.uses_special_alpha_case,
            "loading_type": "monotonic",
            "sign_convention": "compression_positive",
            "reference": RDM_REFERENCE,
            "applicability": {
                "fy_mpa": "200 < fy < 900",
                "diameter_mm": "10 < D < 36",
                "fu_over_fy": "< 2",
                "parameter_p": "<= 4",
                "epsilon_su_over_epsilon_y": "> 14",
                "rb": "8 < rb < 56",
                "l_over_d": ">= 5 for buckling activation",
            },
            "warnings": list(self.applicability_warnings()),
            "provenance": p.provenance.as_dict(),
        }

    def generate_curve(
        self,
        num_points: int = 401,
        max_strain: float | None = None,
    ) -> dict[str, object]:
        """Generate a deterministic curve ending no later than epsilon_su."""

        if num_points < 2:
            raise ConfigError("num_points must be at least 2.")
        stop = self.parameters.epsilon_su if max_strain is None else float(max_strain)
        if not isfinite(stop) or stop <= 0.0:
            raise ConfigError("max_strain must be positive and finite.")
        if stop > self.parameters.epsilon_su:
            raise ConfigError("max_strain cannot exceed epsilon_su for an exported RDM curve.")
        strains = linear_strain_vector(0.0, stop, num_points)
        return {
            "strain": strains,
            "stress": [self.stress_at_strain(strain) for strain in strains],
            "summary": self.summary_parameters(),
        }

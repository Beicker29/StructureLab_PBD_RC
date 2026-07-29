"""Stateful Menegotto-Pinto model following the OpenSees Steel02 history rules."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import fabs
from sys import float_info
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.common import (
    MaterialProvenance,
    UniaxialResponse,
    required_float,
)
from structurelab_pbd_rc.mechanics.materials.protocols import validate_strain_history


@dataclass(frozen=True)
class MenegottoPintoParameters:
    """Explicit Steel02 parameters and applicability metadata."""

    yield_strength_mpa: float
    elastic_modulus_mpa: float
    hardening_ratio: float
    r0: float
    cr1: float
    cr2: float
    a1: float
    a2: float
    a3: float
    a4: float
    diameter_mm: float
    tension_validity_limit: float
    compression_validity_limit: float
    failure_policy: str
    failure_tension_limit: float | None
    failure_compression_limit: float | None
    provenance: MaterialProvenance

    def __post_init__(self) -> None:
        if self.yield_strength_mpa <= 0.0:
            raise ConfigError("parameters.fy_MPa must be positive.")
        if self.elastic_modulus_mpa <= 0.0:
            raise ConfigError("parameters.Es_MPa must be positive.")
        if not 0.0 <= self.hardening_ratio < 1.0:
            raise ConfigError("parameters.b must satisfy 0 <= b < 1.")
        if self.r0 <= 0.0:
            raise ConfigError("parameters.R0 must be positive.")
        if not 0.0 <= self.cr1 <= 1.0:
            raise ConfigError("parameters.cR1 must satisfy 0 <= cR1 <= 1.")
        if self.cr2 <= 0.0:
            raise ConfigError("parameters.cR2 must be positive.")
        if self.a1 < 0.0 or self.a3 < 0.0:
            raise ConfigError("parameters.a1 and parameters.a3 cannot be negative.")
        if self.a2 <= 0.0 or self.a4 <= 0.0:
            raise ConfigError("parameters.a2 and parameters.a4 must be positive.")
        if self.diameter_mm <= 0.0:
            raise ConfigError("parameters.diameter_mm must be positive.")
        if self.compression_validity_limit >= 0.0:
            raise ConfigError("validity.eps_compression_min must be negative.")
        if self.tension_validity_limit <= 0.0:
            raise ConfigError("validity.eps_tension_max must be positive.")
        if self.failure_policy not in {"none", "strain_limit"}:
            raise ConfigError("failure.policy must be 'none' or 'strain_limit'.")
        if self.failure_policy == "strain_limit":
            if self.failure_tension_limit is None or self.failure_tension_limit <= 0.0:
                raise ConfigError("strain_limit failure requires a positive eps_tension_max.")
            if self.failure_compression_limit is None or self.failure_compression_limit >= 0.0:
                raise ConfigError("strain_limit failure requires a negative eps_compression_min.")

    @property
    def yield_strain(self) -> float:
        """Return fy / Es as the Steel02 asymptote parameter."""

        return self.yield_strength_mpa / self.elastic_modulus_mpa

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "MenegottoPintoParameters":
        """Build parameters while rejecting omitted calibration values."""

        require_keys(
            config,
            ("parameters", "validity", "failure", "provenance"),
            context="cyclic model case",
        )
        parameters = config["parameters"]
        validity = config["validity"]
        failure = config["failure"]
        provenance = config["provenance"]
        if not all(isinstance(item, Mapping) for item in (parameters, validity, failure, provenance)):
            raise ConfigError("parameters, validity, failure and provenance must be mappings.")
        require_keys(failure, ("policy",), context="failure")
        failure_policy = str(failure["policy"])

        return cls(
            yield_strength_mpa=required_float(parameters, "fy_MPa", context="parameters"),
            elastic_modulus_mpa=required_float(parameters, "Es_MPa", context="parameters"),
            hardening_ratio=required_float(parameters, "b", context="parameters"),
            r0=required_float(parameters, "R0", context="parameters"),
            cr1=required_float(parameters, "cR1", context="parameters"),
            cr2=required_float(parameters, "cR2", context="parameters"),
            a1=required_float(parameters, "a1", context="parameters"),
            a2=required_float(parameters, "a2", context="parameters"),
            a3=required_float(parameters, "a3", context="parameters"),
            a4=required_float(parameters, "a4", context="parameters"),
            diameter_mm=required_float(parameters, "diameter_mm", context="parameters"),
            tension_validity_limit=required_float(
                validity,
                "eps_tension_max",
                context="validity",
            ),
            compression_validity_limit=required_float(
                validity,
                "eps_compression_min",
                context="validity",
            ),
            failure_policy=failure_policy,
            failure_tension_limit=(
                None
                if failure_policy == "none"
                else required_float(failure, "eps_tension_max", context="failure")
            ),
            failure_compression_limit=(
                None
                if failure_policy == "none"
                else required_float(failure, "eps_compression_min", context="failure")
            ),
            provenance=MaterialProvenance.from_mapping(provenance),
        )


@dataclass
class MenegottoPintoState:
    """Minimal history state used by the Steel02 transition rules."""

    epsmin: float
    epsmax: float
    epspl: float
    epss0: float
    sigs0: float
    epsr: float
    sigr: float
    direction: int
    strain: float
    stress_mpa: float
    tangent_mpa: float
    failed: bool = False


class MenegottoPinto:
    """Steel02-compatible Menegotto-Pinto model with reproducible trial state."""

    model_id = "Cyc_MP"

    def __init__(self, parameters: MenegottoPintoParameters) -> None:
        self.parameters = parameters
        self._committed = self._initial_state()
        self._trial = deepcopy(self._committed)
        self._trial_response = self._response_from_state(
            self._trial,
            reversal=False,
            current_r=parameters.r0,
            xi=0.0,
        )

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "MenegottoPinto":
        """Build a stateful model from one case configuration."""

        return cls(MenegottoPintoParameters.from_config(config))

    def _initial_state(self) -> MenegottoPintoState:
        p = self.parameters
        return MenegottoPintoState(
            epsmin=-p.yield_strain,
            epsmax=p.yield_strain,
            epspl=0.0,
            epss0=0.0,
            sigs0=0.0,
            epsr=0.0,
            sigr=0.0,
            direction=0,
            strain=0.0,
            stress_mpa=0.0,
            tangent_mpa=p.elastic_modulus_mpa,
        )

    def _outside_failure_limit(self, strain: float) -> bool:
        p = self.parameters
        if p.failure_policy != "strain_limit":
            return False
        assert p.failure_tension_limit is not None
        assert p.failure_compression_limit is not None
        return strain > p.failure_tension_limit or strain < p.failure_compression_limit

    def _response_from_state(
        self,
        state: MenegottoPintoState,
        *,
        reversal: bool,
        current_r: float,
        xi: float,
    ) -> UniaxialResponse:
        p = self.parameters
        in_domain = p.compression_validity_limit <= state.strain <= p.tension_validity_limit
        warnings: list[str] = []
        if not in_domain:
            warnings.append(
                "Response is outside the configured experimental validity range and is extrapolated."
            )
        if state.failed:
            warnings.append(
                "Failure is a strain-limit criterion; it is not a low-cycle-fatigue model."
            )
        return UniaxialResponse(
            strain=state.strain,
            stress_mpa=state.stress_mpa,
            tangent_mpa=state.tangent_mpa,
            branch="strain_limit_failure" if state.failed else "menegotto_pinto_transition",
            loading_direction={-1: "negative", 0: "stationary", 1: "positive"}[
                0 if state.strain == self._committed.strain else (1 if state.strain > self._committed.strain else -1)
            ],
            in_domain=in_domain,
            failed=state.failed,
            reversal=reversal,
            diagnostics={
                "current_R": current_r,
                "xi": xi,
                "reversal_strain": state.epsr,
                "reversal_stress_mpa": state.sigr,
                "asymptote_intersection_strain": state.epss0,
                "asymptote_intersection_stress_mpa": state.sigs0,
                "source": p.provenance.source,
                "calibration_status": p.provenance.calibration_status,
            },
            warnings=tuple(warnings),
        )

    def set_trial_strain(self, strain: float) -> UniaxialResponse:
        """Evaluate one trial strain from the last committed state."""

        p = self.parameters
        state = deepcopy(self._committed)
        state.strain = float(strain)
        reversal = False

        if state.failed or self._outside_failure_limit(state.strain):
            state.failed = True
            state.stress_mpa = 0.0
            state.tangent_mpa = 0.0
            self._trial = state
            self._trial_response = self._response_from_state(
                state,
                reversal=False,
                current_r=p.r0,
                xi=0.0,
            )
            return self._trial_response

        deps = state.strain - self._committed.strain
        if state.direction == 0:
            if fabs(deps) < 10.0 * float_info.epsilon:
                state.stress_mpa = 0.0
                state.tangent_mpa = p.elastic_modulus_mpa
                self._trial = state
                self._trial_response = self._response_from_state(
                    state,
                    reversal=False,
                    current_r=p.r0,
                    xi=0.0,
                )
                return self._trial_response
            if deps < 0.0:
                state.direction = 2
                state.epss0 = state.epsmin
                state.sigs0 = -p.yield_strength_mpa
                state.epspl = state.epsmin
            else:
                state.direction = 1
                state.epss0 = state.epsmax
                state.sigs0 = p.yield_strength_mpa
                state.epspl = state.epsmax

        hardening_modulus = p.hardening_ratio * p.elastic_modulus_mpa
        if state.direction == 2 and deps > 0.0:
            reversal = True
            state.direction = 1
            state.epsr = self._committed.strain
            state.sigr = self._committed.stress_mpa
            state.epsmin = min(self._committed.strain, state.epsmin)
            d1 = (state.epsmax - state.epsmin) / (2.0 * p.a4 * p.yield_strain)
            shift = 1.0 + p.a3 * d1**0.8
            state.epss0 = (
                p.yield_strength_mpa * shift
                - hardening_modulus * p.yield_strain * shift
                - state.sigr
                + p.elastic_modulus_mpa * state.epsr
            ) / (p.elastic_modulus_mpa - hardening_modulus)
            state.sigs0 = p.yield_strength_mpa * shift + hardening_modulus * (
                state.epss0 - p.yield_strain * shift
            )
            state.epspl = state.epsmax
        elif state.direction == 1 and deps < 0.0:
            reversal = True
            state.direction = 2
            state.epsr = self._committed.strain
            state.sigr = self._committed.stress_mpa
            state.epsmax = max(self._committed.strain, state.epsmax)
            d1 = (state.epsmax - state.epsmin) / (2.0 * p.a2 * p.yield_strain)
            shift = 1.0 + p.a1 * d1**0.8
            state.epss0 = (
                -p.yield_strength_mpa * shift
                + hardening_modulus * p.yield_strain * shift
                - state.sigr
                + p.elastic_modulus_mpa * state.epsr
            ) / (p.elastic_modulus_mpa - hardening_modulus)
            state.sigs0 = -p.yield_strength_mpa * shift + hardening_modulus * (
                state.epss0 + p.yield_strain * shift
            )
            state.epspl = state.epsmin

        denominator = state.epss0 - state.epsr
        if fabs(denominator) <= float_info.epsilon:
            raise MaterialDomainError("Menegotto-Pinto asymptote intersection is singular.")
        xi = fabs((state.epspl - state.epss0) / p.yield_strain)
        current_r = p.r0 * (1.0 - p.cr1 * xi / (p.cr2 + xi))
        if current_r <= 0.0:
            raise MaterialDomainError("Menegotto-Pinto transition parameter R became non-positive.")
        strain_ratio = (state.strain - state.epsr) / denominator
        transition_base = 1.0 + fabs(strain_ratio) ** current_r
        transition_root = transition_base ** (1.0 / current_r)
        normalized_stress = (
            p.hardening_ratio * strain_ratio
            + (1.0 - p.hardening_ratio) * strain_ratio / transition_root
        )
        state.stress_mpa = normalized_stress * (state.sigs0 - state.sigr) + state.sigr
        normalized_tangent = p.hardening_ratio + (
            1.0 - p.hardening_ratio
        ) / (transition_base * transition_root)
        state.tangent_mpa = normalized_tangent * (state.sigs0 - state.sigr) / denominator

        self._trial = state
        self._trial_response = self._response_from_state(
            state,
            reversal=reversal,
            current_r=current_r,
            xi=xi,
        )
        return self._trial_response

    @property
    def trial_response(self) -> UniaxialResponse:
        """Return the latest trial response."""

        return self._trial_response

    @property
    def committed_state(self) -> MenegottoPintoState:
        """Return a defensive copy of the committed state."""

        return deepcopy(self._committed)

    def commit_state(self) -> None:
        """Confirm the current trial state."""

        self._committed = deepcopy(self._trial)

    def revert_to_last_commit(self) -> UniaxialResponse:
        """Discard trial changes and restore the committed response."""

        self._trial = deepcopy(self._committed)
        self._trial_response = self._response_from_state(
            self._trial,
            reversal=False,
            current_r=self.parameters.r0,
            xi=0.0,
        )
        return self._trial_response

    def reset(self) -> UniaxialResponse:
        """Return committed and trial states to the virgin material state."""

        self._committed = self._initial_state()
        self._trial = deepcopy(self._committed)
        self._trial_response = self._response_from_state(
            self._trial,
            reversal=False,
            current_r=self.parameters.r0,
            xi=0.0,
        )
        return self._trial_response

    def evaluate_history(self, strains: list[float], *, reset: bool = True) -> list[UniaxialResponse]:
        """Evaluate and commit an ordered strain history."""

        history = validate_strain_history(strains)
        if reset:
            self.reset()
        responses: list[UniaxialResponse] = []
        for strain in history:
            response = self.set_trial_strain(strain)
            responses.append(response)
            self.commit_state()
        return responses

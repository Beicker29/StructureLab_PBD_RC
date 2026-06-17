"""Unconfined concrete model interface."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from structurelab_pbd_rc.core.curves import linspace


@dataclass(frozen=True)
class UnconfinedConcreteParameters:
    """Basic parameters for unconfined concrete."""

    f_c_mpa: float
    epsilon_co: float = 0.002
    epsilon_cu: float = 0.004
    elastic_modulus_mpa: float | None = None

    def elastic_modulus(self) -> float:
        """Return Ec using the configured value or 4700 * sqrt(f_c)."""

        if self.elastic_modulus_mpa is not None:
            return self.elastic_modulus_mpa
        return 4700.0 * sqrt(self.f_c_mpa)


class UnconfinedConcreteModel:
    """Placeholder for the future unconfined concrete stress-strain curve."""

    def __init__(self, parameters: UnconfinedConcreteParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Compute positive compression stress for a strain value."""

        if strain < 0.0 or strain > self.parameters.epsilon_cu:
            return 0.0
        f_c = self.parameters.f_c_mpa
        eps_peak = self.parameters.epsilon_co
        ec = self.parameters.elastic_modulus()
        esec = f_c / eps_peak
        r = ec / max(ec - esec, 1e-9)
        x = strain / eps_peak if eps_peak else 0.0
        if x <= 0.0:
            return 0.0
        return f_c * x * r / (r - 1.0 + x**r)

    def generate_curve(self, num_points: int = 401) -> dict[str, object]:
        """Generate the unconfined concrete curve with compression positive."""

        strains = linspace(0.0, self.parameters.epsilon_cu, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        return {
            "name": "unconfined_concrete",
            "strain": strains,
            "stress": stresses,
            "parameters": self.summary_parameters(),
            "warnings": [],
        }

    def summary_parameters(self) -> dict[str, float]:
        """Return parameters used by the model."""

        ec = self.parameters.elastic_modulus()
        esec = self.parameters.f_c_mpa / self.parameters.epsilon_co
        r = ec / max(ec - esec, 1e-9)
        return {
            "f_c_mpa": self.parameters.f_c_mpa,
            "Ec_mpa": ec,
            "epsilon_peak": self.parameters.epsilon_co,
            "epsilon_u": self.parameters.epsilon_cu,
            "Esec_mpa": esec,
            "r": r,
            "sign_convention": "compression_positive",
        }

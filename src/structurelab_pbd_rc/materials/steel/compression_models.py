"""Steel compression model interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.core.curves import linspace


@dataclass(frozen=True)
class SteelCompressionParameters:
    """Parameters for future steel compression model."""

    fy_mpa: float
    elastic_modulus_mpa: float = 200000.0
    epsilon_y: float | None = None
    buckling_enabled: bool = True
    epsilon_buckling: float | None = None
    epsilon_su_compression: float = 0.08
    fu_mpa: float | None = None
    epsilon_sh: float = 0.01
    strain_hardening_modulus_mpa: float = 2000.0
    parameter_p: float = 4.0


class SteelCompressionModel:
    """Future compression model with optional buckling degradation."""

    def __init__(self, parameters: SteelCompressionParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Return positive compression stress without buckling degradation.

        This model intentionally repeats the branch equations instead of
        importing the tension model, so each material model remains independent.
        """

        p = self.summary_parameters()
        eps_y = float(p["eps_y"])
        eps_sh = float(p["eps_sh"])
        eps_su = float(p["eps_su"])
        fy = float(p["fy_mpa"])
        fu = float(p["fu_mpa"])
        es = float(p["Es_mpa"])
        et = float(p["Et_mpa"])
        exponent = float(p["P"])

        if strain < 0.0 or strain > eps_su:
            return 0.0
        if strain <= eps_y:
            return es * strain
        if strain <= eps_sh:
            return fy + et * (strain - eps_y)
        denominator = max(eps_su - eps_sh, 1e-9)
        remaining_ratio = (eps_su - strain) / denominator
        return fu - (fu - fy) * remaining_ratio**max(exponent, 1e-9)

    def summary_parameters(self) -> dict[str, float | str | bool]:
        """Return steel compression parameters."""

        fu = self.parameters.fu_mpa if self.parameters.fu_mpa is not None else 1.15 * self.parameters.fy_mpa
        eps_y = self.parameters.epsilon_y
        if eps_y is None:
            eps_y = self.parameters.fy_mpa / self.parameters.elastic_modulus_mpa
        return {
            "Es_mpa": self.parameters.elastic_modulus_mpa,
            "fy_mpa": self.parameters.fy_mpa,
            "fu_mpa": fu,
            "eps_y": eps_y,
            "eps_sh": max(self.parameters.epsilon_sh, eps_y),
            "eps_su": self.parameters.epsilon_su_compression,
            "Et_mpa": self.parameters.strain_hardening_modulus_mpa,
            "P": self.parameters.parameter_p,
            "buckling_enabled": self.parameters.buckling_enabled,
            "sign_convention": "compression_positive",
        }

    def generate_curve(self, num_points: int = 401, max_strain: float | None = None) -> dict[str, object]:
        """Generate a steel compression curve without buckling degradation."""

        eps_u = float(self.summary_parameters()["eps_su"])
        strains = linspace(0.0, max_strain or eps_u, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        return {
            "name": "steel_compression_no_buckling",
            "strain": strains,
            "stress": stresses,
            "parameters": self.summary_parameters(),
            "warnings": [],
        }

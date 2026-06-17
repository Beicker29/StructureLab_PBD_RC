"""Steel tension model interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.core.curves import linspace


@dataclass(frozen=True)
class SteelTensionParameters:
    """Parameters for future Mander et al. steel tension model."""

    fy_mpa: float
    fu_mpa: float | None = None
    elastic_modulus_mpa: float = 200000.0
    epsilon_y: float | None = None
    strain_hardening_modulus_mpa: float = 2000.0
    epsilon_sh: float = 0.01
    epsilon_su: float = 0.10
    parameter_p: float = 4.0


class ManderSteelTensionModel:
    """Future steel tension model based on Mander et al. 1984."""

    def __init__(self, parameters: SteelTensionParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Return positive steel tension stress."""

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

    def summary_parameters(self) -> dict[str, float | str]:
        """Return steel tension model parameters."""

        fu = self.parameters.fu_mpa if self.parameters.fu_mpa is not None else 1.25 * self.parameters.fy_mpa
        eps_y = self.parameters.epsilon_y
        if eps_y is None:
            eps_y = self.parameters.fy_mpa / self.parameters.elastic_modulus_mpa
        return {
            "Es_mpa": self.parameters.elastic_modulus_mpa,
            "fy_mpa": self.parameters.fy_mpa,
            "fu_mpa": fu,
            "eps_y": eps_y,
            "eps_sh": max(self.parameters.epsilon_sh, eps_y),
            "eps_su": self.parameters.epsilon_su,
            "Et_mpa": self.parameters.strain_hardening_modulus_mpa,
            "P": self.parameters.parameter_p,
            "sign_convention": "tension_positive",
        }

    def generate_curve(self, num_points: int = 401, max_strain: float | None = None) -> dict[str, object]:
        """Generate a steel tension curve."""

        eps_su = float(self.summary_parameters()["eps_su"])
        strains = linspace(0.0, max_strain or eps_su, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        return {
            "name": "steel_tension",
            "strain": strains,
            "stress": stresses,
            "parameters": self.summary_parameters(),
            "warnings": [],
        }

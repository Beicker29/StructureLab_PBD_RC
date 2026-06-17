"""Classic Mander confined concrete model interface."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from structurelab_pbd_rc.core.curves import linspace
from structurelab_pbd_rc.materials.concrete.confinement import ConfinementParameters


@dataclass(frozen=True)
class ManderClassicParameters:
    """Input container for the classic Mander model."""

    f_c_mpa: float
    elastic_modulus_mpa: float
    epsilon_co: float = 0.002
    transverse_steel_ultimate_strain: float = 0.10
    confinement: ConfinementParameters | None = None


class ManderClassicConcreteModel:
    """Future implementation of Mander, Priestley and Park confined concrete."""

    def __init__(self, parameters: ManderClassicParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Return confined concrete stress with compression positive."""

        parameters = self.summary_parameters()
        eps_cu = float(parameters["eps_cu"])
        if strain < 0.0 or strain > eps_cu:
            return 0.0
        eps_cc = float(parameters["eps_cc"])
        fcc = float(parameters["fcc_mpa"])
        r = float(parameters["r"])
        x = strain / eps_cc if eps_cc else 0.0
        if x <= 0.0:
            return 0.0
        return fcc * x * r / (r - 1.0 + x**r)

    def summary_parameters(self) -> dict[str, float]:
        """Return classic Mander confined concrete parameters."""

        fc = self.parameters.f_c_mpa
        ec = self.parameters.elastic_modulus_mpa
        confinement = self.parameters.confinement
        rho_s = confinement.rho_s if confinement else 0.0
        ke = confinement.ke if confinement else 0.0
        fl_eff = confinement.fl_eff_mpa if confinement else 0.0
        fyh = confinement.transverse_yield_strength_mpa if confinement else 0.0

        ratio = fl_eff / fc if fc else 0.0
        fcc = fc * (-1.254 + 2.254 * sqrt(1.0 + 7.94 * ratio) - 2.0 * ratio)
        fcc = max(fcc, fc)
        eps_cc = self.parameters.epsilon_co * (1.0 + 5.0 * (fcc / fc - 1.0))
        eps_cu = 0.004 + 1.4 * rho_s * fyh * self.parameters.transverse_steel_ultimate_strain / fcc
        eps_cu = max(eps_cu, eps_cc * 1.05)
        esec = fcc / eps_cc
        r = ec / max(ec - esec, 1e-9)
        return {
            "f_c_mpa": fc,
            "fcc_mpa": fcc,
            "eps_cc": eps_cc,
            "eps_cu": eps_cu,
            "Ec_mpa": ec,
            "Esec_mpa": esec,
            "r": r,
            "rho_s": rho_s,
            "ke": ke,
            "fl_eff_mpa": fl_eff,
            "fyh_mpa": fyh,
            "sign_convention": "compression_positive",
        }

    def generate_curve(self, num_points: int = 401) -> dict[str, object]:
        """Generate the classic Mander stress-strain curve."""

        eps_cu = float(self.summary_parameters()["eps_cu"])
        strains = linspace(0.0, eps_cu, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        return {
            "name": "mander_classic",
            "strain": strains,
            "stress": stresses,
            "parameters": self.summary_parameters(),
            "warnings": [],
        }

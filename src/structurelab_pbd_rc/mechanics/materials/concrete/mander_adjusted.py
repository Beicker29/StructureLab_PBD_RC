"""Adjusted Mander confined concrete model interface."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.core.curves import linspace
from structurelab_pbd_rc.mechanics.materials.concrete.confinement import ConfinementParameters
from structurelab_pbd_rc.mechanics.materials.concrete.equations import (
    mander_adjusted_confined_strength,
    mander_adjusted_transverse_strain,
    mander_adjusted_ultimate_strain,
    mander_peak_strain,
    mander_r_parameter,
    secant_modulus,
)


@dataclass(frozen=True)
class ManderAdjustedParameters:
    """Input container for the adjusted Mander model used in the course."""

    f_c_mpa: float
    elastic_modulus_mpa: float
    epsilon_co: float = 0.002
    transverse_steel_ultimate_strain: float = 0.10
    confinement: ConfinementParameters | None = None


class ManderAdjustedConcreteModel:
    """Future adjusted Mander implementation."""

    def __init__(self, parameters: ManderAdjustedParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Return confined concrete stress using the adjusted Mander form."""

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
        """Return adjusted Mander confined concrete parameters."""

        fc = self.parameters.f_c_mpa
        ec = self.parameters.elastic_modulus_mpa
        confinement = self.parameters.confinement
        rho_s = confinement.rho_s if confinement else 0.0
        ke = confinement.ke if confinement else 0.0
        fl_eff = confinement.fl_eff_mpa if confinement else 0.0
        fyh = confinement.transverse_yield_strength_mpa if confinement else 0.0

        fcc = mander_adjusted_confined_strength(f_co=fc, fl=fl_eff)
        fcc = max(fcc, fc)
        eps_cc = mander_peak_strain(epsilon_co=self.parameters.epsilon_co, fcc=fcc, f_co=fc)
        eps_tst = mander_adjusted_transverse_strain(epsilon_su=self.parameters.transverse_steel_ultimate_strain)
        eps_cu = mander_adjusted_ultimate_strain(rho_s=rho_s, fyh=fyh, epsilon_tst=eps_tst, fcc=fcc)
        eps_cu = max(eps_cu, eps_cc * 1.05)
        esec = secant_modulus(stress=fcc, strain=eps_cc)
        r = mander_r_parameter(elastic_modulus=ec, secant_elastic_modulus=esec)
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
            "eps_tst": eps_tst,
            "sign_convention": "compression_positive",
        }

    def generate_curve(self, num_points: int = 401) -> dict[str, object]:
        """Generate the adjusted Mander stress-strain curve."""

        eps_cu = float(self.summary_parameters()["eps_cu"])
        strains = linspace(0.0, eps_cu, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        return {
            "name": "mander_adjusted_confined_concrete",
            "strain": strains,
            "stress": stresses,
            "parameters": self.summary_parameters(),
            "warnings": [],
        }


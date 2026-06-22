"""Attard-Setunge concrete model."""

from __future__ import annotations

from dataclasses import dataclass
from math import log

from structurelab_pbd_rc.core.curves import linspace


@dataclass(frozen=True)
class AttardSetungeParameters:
    """Input container for the Attard-Setunge model."""

    f_c_mpa: float
    elastic_modulus_mpa: float
    epsilon_peak: float = 0.002
    epsilon_u: float = 0.004
    confined: bool = False
    confinement_pressure_mpa: float | None = None
    confined_strength_mpa: float | None = None
    confined_peak_strain: float | None = None
    confined_ultimate_strain: float | None = None


class AttardSetungeConcreteModel:
    """Attard-Setunge stress-strain model with compression positive."""

    def __init__(self, parameters: AttardSetungeParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Return concrete stress with compression positive."""

        params = self.summary_parameters()
        eps_u = float(params["epsilon_u"])
        if strain < 0.0 or strain > eps_u:
            return 0.0

        f_peak = float(params["f_peak_mpa"])
        eps_peak = float(params["epsilon_peak"])
        x = strain / eps_peak if eps_peak else 0.0
        if x <= 0.0:
            return 0.0
        if x <= 1.0:
            a, b, c, d = self.ascending_coefficients()
        else:
            a, b, c, d = self.descending_coefficients()
        denominator = max(1.0 + c * x + d * x * x, 1e-9)
        stress = f_peak * (a * x + b * x * x) / denominator
        return max(stress, 0.0)

    def ascending_coefficients(self) -> tuple[float, float, float, float]:
        """Return As, Bs, Cs and Ds for the ascending branch.

        The confined and unconfined cases use the same expressions; confinement
        only changes the peak stress and peak strain through `fl`.
        """

        params = self.summary_parameters()
        a = float(params["Eti_mpa"]) * float(params["epsilon_peak"]) / float(params["f_peak_mpa"])
        alpha = float(params["alpha"])
        fpl_ratio = float(params["fpl_mpa"]) / float(params["f_peak_mpa"])
        one_minus = max(1.0 - fpl_ratio, 1e-9)
        b = ((a - 1.0) ** 2) / (alpha * one_minus**2)
        b += (a**2 * (1.0 - alpha)) / (alpha**2 * max(fpl_ratio, 1e-9) * one_minus)
        b -= 1.0
        c = a - 2.0
        d = b + 1.0
        return a, b, c, d

    def descending_coefficients(self) -> tuple[float, float, float, float]:
        """Return rational coefficients for the descending branch."""

        params = self.summary_parameters()
        if not self.parameters.confined:
            eps_cc = float(params["epsilon_peak"])
            eps_ic = float(params["epsilon_ic"])
            fc = float(params["f_peak_mpa"])
            f_ic = float(params["f_ic_mpa"])
            denominator = max(eps_cc * eps_ic * (fc - f_ic), 1e-9)
            a = f_ic * (eps_ic - eps_cc) ** 2 / denominator
            b = 0.0
            c = a - 2.0
            d = 1.0
            return a, b, c, d

        eps_cc = float(params["epsilon_peak"])
        fcc = float(params["f_peak_mpa"])
        fi = float(params["fi_mpa"])
        eps_i = float(params["epsilon_i"])
        f_2i = float(params["f_2i_mpa"])
        eps_2i = float(params["epsilon_2i"])
        ei = fi / max(eps_i, 1e-9)
        e2i = f_2i / max(eps_2i, 1e-9)
        fcc_minus_fi = max(fcc - fi, 1e-9)
        fcc_minus_f2i = max(fcc - f_2i, 1e-9)
        a = ((eps_2i - eps_i) / eps_cc) * (
            (eps_2i * ei) / fcc_minus_fi - (4.0 * eps_i * e2i) / fcc_minus_f2i
        )
        b = (eps_i - eps_2i) * (ei / fcc_minus_fi - 4.0 * e2i / fcc_minus_f2i)
        c = a - 2.0
        d = b + 1.0
        return a, b, c, d

    def summary_parameters(self) -> dict[str, object]:
        """Return Attard-Setunge parameter summary."""

        f_c = self.parameters.f_c_mpa
        ec = self.parameters.elastic_modulus_mpa
        eps_co = self.parameters.epsilon_peak
        fl = max(self.parameters.confinement_pressure_mpa or 0.0, 0.0)
        fl_ratio = fl / f_c if f_c else 0.0

        alpha = 1.17 - 0.002125 * (f_c - 20.0)
        alpha = min(max(alpha, 1.00), 1.17)
        eti = alpha * ec

        if self.parameters.confined:
            f_peak = self.parameters.confined_strength_mpa
            if f_peak is None:
                f_peak = f_c * (1.0 + 10.0 * fl_ratio**0.6)
            eps_peak = self.parameters.confined_peak_strain
            if eps_peak is None:
                eps_peak = eps_co * (1.0 + (69.4 - 13.2 * log(max(f_c, 1e-9))) * fl_ratio)

            denominator_fi = 5.06 * max(fl_ratio, 1e-12) ** 0.57 + 1.0
            denominator_eps_i = 1.12 * max(fl_ratio, 1e-12) ** 0.26 + 1.0
            denominator_f2i = 6.35 * max(fl_ratio, 1e-12) ** 0.62 + 1.0
            fi = f_peak * ((0.41 - 0.17 * log(max(f_c, 1e-9))) / denominator_fi + 1.0)
            eps_i = eps_peak * ((0.5 - 0.3 * log(max(f_c, 1e-9))) / denominator_eps_i + 2.0)
            f_2i = f_peak * ((0.45 - 0.25 * log(max(f_c, 1e-9))) / denominator_f2i + 1.0)
            eps_2i = 2.0 * eps_i - eps_peak
            eps_u = self.parameters.confined_ultimate_strain
            if eps_u is None:
                eps_u = eps_2i
        else:
            f_peak = f_c
            eps_peak = eps_co
            eps_u = self.parameters.epsilon_u
            fi = None
            eps_i = None
            f_2i = None
            eps_2i = None

        fpl = 0.45 * f_c
        f_ic = f_c * (1.41 - 0.17 * log(max(f_c, 1e-9)))
        eps_ic = eps_co * (2.5 - 0.3 * log(max(f_c, 1e-9)))
        warnings: list[str] = []
        if self.parameters.confined and eps_2i is not None and eps_u < eps_2i:
            warnings.append("Confined Attard-Setunge epsilon_u was increased to epsilon_2i.")
            eps_u = eps_2i
        return {
            "f_c_mpa": f_c,
            "f_peak_mpa": f_peak,
            "epsilon_peak": eps_peak,
            "epsilon_u": max(eps_u, eps_peak * 1.05),
            "Ec_mpa": self.parameters.elastic_modulus_mpa,
            "alpha": alpha,
            "Eti_mpa": eti,
            "fpl_mpa": fpl,
            "f_ic_mpa": f_ic,
            "epsilon_ic": eps_ic,
            "confined": self.parameters.confined,
            "confinement_pressure_mpa": self.parameters.confinement_pressure_mpa,
            "fl_over_fc": fl_ratio,
            "fi_mpa": fi,
            "epsilon_i": eps_i,
            "f_2i_mpa": f_2i,
            "epsilon_2i": eps_2i,
            "warnings": warnings,
            "sign_convention": "compression_positive",
        }

    def generate_curve(self, num_points: int = 401) -> dict[str, object]:
        """Generate the Attard-Setunge curve."""

        eps_u = float(self.summary_parameters()["epsilon_u"])
        strains = linspace(0.0, eps_u, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        name = "attard_setunge_confined_concrete" if self.parameters.confined else "attard_setunge_unconfined_concrete"
        params = self.summary_parameters()
        return {
            "name": name,
            "strain": strains,
            "stress": stresses,
            "parameters": params,
            "warnings": list(params["warnings"]),
        }

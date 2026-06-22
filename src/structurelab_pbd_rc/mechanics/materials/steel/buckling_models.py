"""Buckling model interfaces for longitudinal reinforcing bars."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

from structurelab_pbd_rc.core.curves import linspace


@dataclass(frozen=True)
class BarBucklingParameters:
    """Inputs related to spacing-to-diameter sensitivity."""

    transverse_spacing_cm: float
    longitudinal_bar_diameter_mm: float
    fy_mpa: float = 470.0
    elastic_modulus_mpa: float = 200000.0
    epsilon_y: float | None = None
    degradation_alpha: float = 3.0
    ultimate_strain: float = 0.08


def estimate_pre_buckling_strain(parameters: BarBucklingParameters) -> float:
    """Estimate strain before buckling.

    Uses the expression from the Taller 1 PDF with s/db in consistent units.
    """

    ratio = spacing_to_diameter_ratio(parameters)
    return max(0.10 - 0.0146 * ratio + 0.00062 * ratio**2, 0.002)


def spacing_to_diameter_ratio(parameters: BarBucklingParameters) -> float:
    """Return transverse spacing divided by longitudinal bar diameter."""

    return (parameters.transverse_spacing_cm * 10.0) / parameters.longitudinal_bar_diameter_mm


def estimate_buckling_strength_ratio(parameters: BarBucklingParameters) -> float:
    """Estimate fbb/fy from the Taller 1 PDF expression."""

    ratio = spacing_to_diameter_ratio(parameters)
    return max(1.105 - 0.0211 * ratio - 0.00517 * ratio**2, 0.05)


class BucklingSteelCompressionModel:
    """Compression steel curve with post-buckling exponential degradation."""

    def __init__(self, parameters: BarBucklingParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Return positive compression stress with buckling degradation."""

        p = self.summary_parameters()
        eps_y = float(p["eps_y"])
        eps_b = float(p["eps_buckling"])
        eps_u = float(p["eps_u"])
        fy = float(p["fy_mpa"])
        fbb = float(p["fbb_mpa"])
        es = float(p["Es_mpa"])
        alpha = float(p["alpha"])

        if strain < 0.0 or strain > eps_u:
            return 0.0
        if strain <= eps_y:
            return es * strain
        if strain <= eps_b:
            # TODO: Confirm whether fy-to-fbb reduction is immediate or gradual up to eps_buckling.
            return min(fy, fbb)
        degradation_range = max(eps_u - eps_b, 1e-9)
        return fbb * exp(-alpha * (strain - eps_b) / degradation_range)

    def summary_parameters(self) -> dict[str, float | str]:
        """Return buckling model parameters."""

        ratio = spacing_to_diameter_ratio(self.parameters)
        strength_ratio = estimate_buckling_strength_ratio(self.parameters)
        eps_b = estimate_pre_buckling_strain(self.parameters)
        eps_y = self.parameters.epsilon_y
        if eps_y is None:
            eps_y = self.parameters.fy_mpa / self.parameters.elastic_modulus_mpa
        eps_u = max(self.parameters.ultimate_strain, eps_b * 1.05)
        return {
            "s_over_db": ratio,
            "fbb_over_fy": strength_ratio,
            "fbb_mpa": strength_ratio * self.parameters.fy_mpa,
            "eps_buckling": eps_b,
            "alpha": self.parameters.degradation_alpha,
            "eps_u": eps_u,
            "fy_mpa": self.parameters.fy_mpa,
            "Es_mpa": self.parameters.elastic_modulus_mpa,
            "eps_y": eps_y,
            "sign_convention": "compression_positive",
        }

    def generate_curve(self, num_points: int = 401, max_strain: float | None = None) -> dict[str, object]:
        """Generate a steel compression curve with buckling degradation."""

        eps_u = float(self.summary_parameters()["eps_u"])
        strains = linspace(0.0, max_strain or eps_u, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        return {
            "name": "steel_compression_with_buckling",
            "strain": strains,
            "stress": stresses,
            "parameters": self.summary_parameters(),
            "warnings": [],
        }

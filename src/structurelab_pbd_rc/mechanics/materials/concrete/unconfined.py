"""Unconfined concrete model interface."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from structurelab_pbd_rc.core.curves import linspace


@dataclass(frozen=True)
class UnconfinedConcreteParameters:
    """Basic parameters for Mander unconfined concrete."""

    f_c_mpa: float
    epsilon_co: float = 0.002
    epsilon_sp: float = 0.005
    elastic_modulus_mpa: float | None = None
    tensile_strength_mpa: float | None = None
    tensile_modulus_mpa: float | None = None

    def elastic_modulus(self) -> float:
        """Return Ec using the configured value or 4700 * sqrt(f_co)."""

        if self.elastic_modulus_mpa is not None:
            return self.elastic_modulus_mpa
        return 4700.0 * sqrt(self.f_c_mpa)

    def tensile_strength(self) -> float:
        """Return ft using the configured value or 0.62 * sqrt(f_co)."""

        if self.tensile_strength_mpa is not None:
            return self.tensile_strength_mpa
        return 0.62 * sqrt(self.f_c_mpa)

    def tensile_modulus(self) -> float:
        """Return Et for concrete tension, equal to Ec by default."""

        if self.tensile_modulus_mpa is not None:
            return self.tensile_modulus_mpa
        return self.elastic_modulus()


class UnconfinedConcreteModel:
    """Mander unconfined concrete stress-strain curve."""

    def __init__(self, parameters: UnconfinedConcreteParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Compute concrete stress using compression-positive convention."""

        ft = self.parameters.tensile_strength()
        et = self.parameters.tensile_modulus()
        eps_t = ft / max(et, 1e-9)
        if -eps_t <= strain < 0.0:
            return et * strain
        if strain > self.parameters.epsilon_sp:
            return 0.0
        f_c = self.parameters.f_c_mpa
        eps_peak = self.parameters.epsilon_co
        ec = self.parameters.elastic_modulus()
        esec = f_c / eps_peak
        r = ec / max(ec - esec, 1e-9)
        x = strain / eps_peak if eps_peak else 0.0
        if x <= 0.0:
            return 0.0
        if strain <= 2.0 * eps_peak:
            return f_c * x * r / (r - 1.0 + x**r)

        stress_at_2eco = f_c * 2.0 * r / (r - 1.0 + 2.0**r)
        descending_range = max(self.parameters.epsilon_sp - 2.0 * eps_peak, 1e-9)
        remaining_ratio = max((self.parameters.epsilon_sp - strain) / descending_range, 0.0)
        return stress_at_2eco * remaining_ratio

    def generate_curve(
        self,
        num_points: int = 401,
        *,
        include_tension_branch: bool = False,
        tension_sign: str = "positive",
    ) -> dict[str, object]:
        """Generate the unconfined concrete curve.

        Compression is always positive. When requested by the YAML sign
        convention, the tensile branch is prepended with negative strain and
        negative stress.
        """

        compression_strains = linspace(0.0, self.parameters.epsilon_sp, num_points)
        strains = compression_strains
        stresses = [self.stress_at_strain(strain) for strain in compression_strains]
        params = self.summary_parameters()

        if include_tension_branch and tension_sign == "negative":
            tension_point_count = max(2, min(41, num_points // 10))
            epsilon_t = float(params["epsilon_t"])
            tension_strains = linspace(-epsilon_t, 0.0, tension_point_count)
            tension_stresses = [self.stress_at_strain(strain) for strain in tension_strains]
            strains = tension_strains + compression_strains[1:]
            stresses = tension_stresses + stresses[1:]
            params["tension_sign_convention"] = "negative"
            params["epsilon_t_plot"] = -epsilon_t
            params["ft_plot_mpa"] = -float(params["ft_mpa"])
        else:
            params["tension_sign_convention"] = "positive"
            params["epsilon_t_plot"] = float(params["epsilon_t"])
            params["ft_plot_mpa"] = float(params["ft_mpa"])

        return {
            "name": "mander_classic_unconfined_concrete",
            "strain": strains,
            "stress": stresses,
            "parameters": params,
            "warnings": [],
        }

    def summary_parameters(self) -> dict[str, float]:
        """Return parameters used by the model."""

        ec = self.parameters.elastic_modulus()
        esec = self.parameters.f_c_mpa / self.parameters.epsilon_co
        r = ec / max(ec - esec, 1e-9)
        ft = self.parameters.tensile_strength()
        et = self.parameters.tensile_modulus()
        eps_t = ft / max(et, 1e-9)
        return {
            "f_co_mpa": self.parameters.f_c_mpa,
            "Ec_mpa": ec,
            "epsilon_peak": self.parameters.epsilon_co,
            "epsilon_2co": 2.0 * self.parameters.epsilon_co,
            "epsilon_sp": self.parameters.epsilon_sp,
            "epsilon_u": self.parameters.epsilon_sp,
            "ft_mpa": ft,
            "Et_mpa": et,
            "epsilon_t": eps_t,
            "Esec_mpa": esec,
            "r": r,
            "sign_convention": "compression_positive",
        }

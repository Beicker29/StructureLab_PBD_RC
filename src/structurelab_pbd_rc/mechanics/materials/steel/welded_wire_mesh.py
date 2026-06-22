"""Welded wire mesh model interface."""

from __future__ import annotations

from dataclasses import dataclass

from structurelab_pbd_rc.core.curves import linspace


@dataclass(frozen=True)
class WeldedWireMeshParameters:
    """Parameters for welded wire mesh stress-strain curves."""

    diameter_mm: int
    fy_mpa: float
    fu_mpa: float
    epsilon_u: float
    elastic_modulus_mpa: float = 200000.0


class CarrilloWeldedWireMeshModel:
    """Future welded wire mesh model using Carrillo et al. 2019 parameters."""

    def __init__(self, parameters: WeldedWireMeshParameters) -> None:
        self.parameters = parameters

    def stress_at_strain(self, strain: float) -> float:
        """Return welded wire mesh tension stress.

        The PDF gives a compact high-order expression. This implementation uses
        the readable form `Es*eps + (fu - Es*eps_u)*(eps/eps_u)^20`. The `fu`
        value comes from the mesh database by diameter and the returned stress
        is capped at that diameter-specific ultimate stress.
        """

        eps_u = self.parameters.epsilon_u
        if strain < 0.0 or strain > eps_u:
            return 0.0
        if eps_u <= 0.0:
            return 0.0
        stress = self.parameters.elastic_modulus_mpa * strain
        stress += (self.parameters.fu_mpa - self.parameters.elastic_modulus_mpa * eps_u) * (strain / eps_u) ** 20
        return max(min(stress, self.parameters.fu_mpa), 0.0)

    def summary_parameters(self) -> dict[str, float | int | str]:
        """Return welded wire mesh parameters."""

        return {
            "diameter_mm": self.parameters.diameter_mm,
            "fy_mpa": self.parameters.fy_mpa,
            "fu_mpa": self.parameters.fu_mpa,
            "epsilon_u": self.parameters.epsilon_u,
            "Es_mpa": self.parameters.elastic_modulus_mpa,
            "sign_convention": "tension_positive",
            "equation_note": "fu_mpa is selected from the mesh database by diameter; stress is capped at this diameter-specific fu.",
        }

    def generate_curve(self, num_points: int = 401, max_strain: float | None = None) -> dict[str, object]:
        """Generate a welded wire mesh stress-strain curve."""

        eps_u = self.parameters.epsilon_u
        strains = linspace(0.0, max_strain or eps_u, num_points)
        stresses = [self.stress_at_strain(strain) for strain in strains]
        return {
            "name": "welded_wire_mesh",
            "strain": strains,
            "stress": stresses,
            "parameters": self.summary_parameters(),
            "warnings": [
                "Mesh equation is capped at the diameter-specific fu to avoid nonphysical overshoot."
            ],
        }

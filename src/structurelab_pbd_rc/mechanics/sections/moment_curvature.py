"""Moment-curvature bilinearization tools."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from structurelab_pbd_rc.mechanics.idealization import (
    BackbonePoint,
    EnergyEquivalentSettings,
    bilinearize_energy_equivalent,
    clean_positive_backbone,
    interpolate_response,
)


@dataclass(frozen=True)
class MomentCurvaturePoint:
    """A point in a moment-curvature diagram."""

    phi: float
    moment: float


@dataclass(frozen=True)
class BilinearizationSettings:
    """Settings for ASCE/FEMA-style M-phi bilinearization."""

    stiffness_fraction: float = 0.60
    tolerance: float = 0.005
    search_points: int = 5000
    my_lower_ratio: float = 0.05
    my_upper_ratio: float = 1.00


def _clean_positive_curve(points: Iterable[MomentCurvaturePoint]) -> list[MomentCurvaturePoint]:
    """Return a sorted positive-backbone curve from signed or unsigned points."""

    backbone = clean_positive_backbone(
        BackbonePoint(deformation=point.phi, response=point.moment)
        for point in points
    )
    return [
        MomentCurvaturePoint(
            phi=point.deformation,
            moment=point.response,
        )
        for point in backbone
    ]


def _interpolate_moment(points: list[MomentCurvaturePoint], phi: float) -> float:
    """Interpolate moment at a given curvature."""

    return interpolate_response(
        [
            BackbonePoint(
                deformation=point.phi,
                response=point.moment,
            )
            for point in points
        ],
        phi,
    )


def truncate_moment_curvature_curve_at_point(
    points: Iterable[MomentCurvaturePoint],
    *,
    phi_u: float,
    moment_u: float,
) -> list[MomentCurvaturePoint]:
    """Return a positive backbone truncated at a user-defined endpoint."""

    adopted_phi_u = abs(float(phi_u))
    adopted_moment_u = abs(float(moment_u))
    if not (isfinite(adopted_phi_u) and isfinite(adopted_moment_u)):
        raise ValueError("Cyclic endpoint must contain finite phi_u and moment_u values.")
    if adopted_phi_u <= 0.0:
        raise ValueError("Cyclic endpoint phi_u must be positive.")

    curve = _clean_positive_curve(points)
    if adopted_phi_u > curve[-1].phi + 1e-12:
        raise ValueError("Cyclic endpoint phi_u exceeds the available curve domain.")

    truncated: list[MomentCurvaturePoint] = []
    for point in curve:
        if point.phi < adopted_phi_u - 1e-12:
            truncated.append(point)
            continue
        truncated.append(MomentCurvaturePoint(phi=adopted_phi_u, moment=adopted_moment_u))
        break

    if not truncated:
        truncated.append(MomentCurvaturePoint(phi=0.0, moment=0.0))
    if truncated[-1].phi < adopted_phi_u - 1e-12:
        truncated.append(MomentCurvaturePoint(phi=adopted_phi_u, moment=adopted_moment_u))
    return truncated


def _default_ultimate_point(
    points: list[MomentCurvaturePoint],
    *,
    post_peak_strength_ratio: float,
) -> tuple[float, float, str]:
    """Select phi_u at the first post-peak strength drop, or at the final point."""

    peak_index = max(range(len(points)), key=lambda index: points[index].moment)
    peak = points[peak_index]
    threshold = post_peak_strength_ratio * peak.moment

    for index in range(peak_index + 1, len(points)):
        left = points[index - 1]
        right = points[index]
        if right.moment <= threshold:
            if abs(right.moment - left.moment) <= 1e-15:
                return right.phi, right.moment, "first_post_peak_strength_drop"
            ratio = (threshold - left.moment) / (right.moment - left.moment)
            phi_u = left.phi + ratio * (right.phi - left.phi)
            return phi_u, threshold, "first_post_peak_strength_drop"

    return points[-1].phi, points[-1].moment, "final_valid_point"


def bilinearize_moment_curvature(
    points: Iterable[MomentCurvaturePoint],
    *,
    phi_u: float | None = None,
    post_peak_strength_ratio: float = 0.80,
    settings: BilinearizationSettings | None = None,
) -> dict[str, object]:
    """Idealize a moment-curvature curve with an ASCE/FEMA-style bilinear curve."""

    config = settings or BilinearizationSettings()
    curve = _clean_positive_curve(points)

    if phi_u is None:
        adopted_phi_u, adopted_moment_u, ultimate_mode = _default_ultimate_point(
            curve,
            post_peak_strength_ratio=post_peak_strength_ratio,
        )
    else:
        adopted_phi_u = float(phi_u)
        adopted_moment_u = _interpolate_moment(curve, adopted_phi_u)
        ultimate_mode = "user_defined_phi_u"

    generic = bilinearize_energy_equivalent(
        (
            BackbonePoint(
                deformation=point.phi,
                response=point.moment,
            )
            for point in curve
        ),
        deformation_u=adopted_phi_u,
        settings=EnergyEquivalentSettings(
            stiffness_fraction=config.stiffness_fraction,
            tolerance=config.tolerance,
            search_points=max(config.search_points, 2),
            yield_lower_ratio=config.my_lower_ratio,
            yield_upper_ratio=config.my_upper_ratio,
        ),
    )
    generic_parameters = generic["parameters"]
    generic_area = generic["area"]
    generic_peak = generic["peak"]
    generic_actual = generic["actual_curve"]
    generic_bilinear = generic["bilinear_curve"]

    return {
        "method": "asce_fema_energy_equivalent_m_phi",
        "status": generic["status"],
        "settings": {
            "stiffness_fraction": config.stiffness_fraction,
            "tolerance": config.tolerance,
            "search_points": config.search_points,
            "my_lower_ratio": config.my_lower_ratio,
            "my_upper_ratio": config.my_upper_ratio,
            "post_peak_strength_ratio": post_peak_strength_ratio,
        },
        "peak": {
            "phi": generic_peak["deformation"],
            "moment": generic_peak["response"],
        },
        "ultimate": {"phi": adopted_phi_u, "moment": adopted_moment_u, "mode": ultimate_mode},
        "area": {
            "A_real": generic_area["actual"],
            "A_bilinear": generic_area["bilinear"],
        },
        "parameters": {
            "Ke": generic_parameters["effective_stiffness"],
            "My": generic_parameters["yield_response"],
            "phi_y": generic_parameters["yield_deformation"],
            "Kp": generic_parameters["post_yield_stiffness"],
            "alpha": generic_parameters["alpha"],
            "Mu": adopted_moment_u,
            "phi_u": adopted_phi_u,
            "M_60My": generic_parameters["fraction_response"],
            "phi_60My": generic_parameters["fraction_deformation"],
            "relative_error": generic_parameters["relative_error"],
            "absolute_relative_error": generic_parameters[
                "absolute_relative_error"
            ],
            "ductility_phi": generic_parameters["ductility"],
        },
        "actual_curve": [
            {
                "phi": point["deformation"],
                "moment": point["response"],
            }
            for point in generic_actual
        ],
        "bilinear_curve": [
            {
                "point": point["point"],
                "phi": point["deformation"],
                "moment": point["response"],
            }
            for point in generic_bilinear
        ],
    }

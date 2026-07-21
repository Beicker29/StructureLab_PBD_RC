"""Moment-curvature bilinearization tools."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable


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

    cleaned: list[MomentCurvaturePoint] = []
    for point in points:
        phi = abs(float(point.phi))
        moment = abs(float(point.moment))
        if not (isfinite(phi) and isfinite(moment)):
            continue
        cleaned.append(MomentCurvaturePoint(phi=phi, moment=moment))

    cleaned.sort(key=lambda point: point.phi)
    if not cleaned:
        raise ValueError("Moment-curvature curve has no valid numeric points.")

    merged: list[MomentCurvaturePoint] = []
    for point in cleaned:
        if merged and abs(point.phi - merged[-1].phi) <= 1e-12:
            if point.moment >= merged[-1].moment:
                merged[-1] = point
        else:
            merged.append(point)

    if merged[0].phi > 0.0:
        merged.insert(0, MomentCurvaturePoint(phi=0.0, moment=0.0))
    elif abs(merged[0].phi) <= 1e-12 and abs(merged[0].moment) > 1e-12:
        merged[0] = MomentCurvaturePoint(phi=0.0, moment=0.0)

    return merged


def _interpolate_moment(points: list[MomentCurvaturePoint], phi: float) -> float:
    """Interpolate moment at a given curvature."""

    if phi <= points[0].phi:
        return points[0].moment
    if phi >= points[-1].phi:
        return points[-1].moment

    for index in range(1, len(points)):
        left = points[index - 1]
        right = points[index]
        if left.phi <= phi <= right.phi:
            ratio = (phi - left.phi) / max(right.phi - left.phi, 1e-15)
            return left.moment + ratio * (right.moment - left.moment)
    return points[-1].moment


def _interpolate_phi_on_ascending_branch(points: list[MomentCurvaturePoint], moment: float) -> float:
    """Interpolate curvature for a moment on the ascending branch."""

    peak_index = max(range(len(points)), key=lambda index: points[index].moment)
    ascending = points[: peak_index + 1]
    for index in range(1, len(ascending)):
        left = ascending[index - 1]
        right = ascending[index]
        lower = min(left.moment, right.moment)
        upper = max(left.moment, right.moment)
        if lower <= moment <= upper and abs(right.moment - left.moment) > 1e-15:
            ratio = (moment - left.moment) / (right.moment - left.moment)
            return left.phi + ratio * (right.phi - left.phi)
    raise ValueError(f"Moment {moment} is outside the ascending branch.")


def _truncate_at_phi(points: list[MomentCurvaturePoint], phi_u: float) -> list[MomentCurvaturePoint]:
    """Return points from zero to phi_u, including an interpolated endpoint."""

    if phi_u <= 0.0:
        raise ValueError("Ultimate curvature phi_u must be positive.")
    if phi_u > points[-1].phi + 1e-12:
        raise ValueError("Ultimate curvature phi_u exceeds the available curve domain.")

    truncated: list[MomentCurvaturePoint] = []
    for point in points:
        if point.phi < phi_u:
            truncated.append(point)
        elif abs(point.phi - phi_u) <= 1e-12:
            truncated.append(point)
            break
        else:
            truncated.append(MomentCurvaturePoint(phi=phi_u, moment=_interpolate_moment(points, phi_u)))
            break

    if truncated[-1].phi < phi_u:
        truncated.append(MomentCurvaturePoint(phi=phi_u, moment=_interpolate_moment(points, phi_u)))
    return truncated


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


def _trapezoidal_area(points: list[MomentCurvaturePoint]) -> float:
    """Calculate area under a moment-curvature curve."""

    area = 0.0
    for index in range(1, len(points)):
        left = points[index - 1]
        right = points[index]
        area += 0.5 * (left.moment + right.moment) * (right.phi - left.phi)
    return area


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


def _candidate_values(start: float, stop: float, count: int) -> Iterable[float]:
    """Yield linearly spaced values without requiring NumPy."""

    if count <= 1:
        yield stop
        return
    step = (stop - start) / (count - 1)
    for index in range(count):
        yield start + index * step


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
    peak_index = max(range(len(curve)), key=lambda index: curve[index].moment)
    peak = curve[peak_index]

    if phi_u is None:
        adopted_phi_u, adopted_moment_u, ultimate_mode = _default_ultimate_point(
            curve,
            post_peak_strength_ratio=post_peak_strength_ratio,
        )
    else:
        adopted_phi_u = float(phi_u)
        adopted_moment_u = _interpolate_moment(curve, adopted_phi_u)
        ultimate_mode = "user_defined_phi_u"

    truncated = _truncate_at_phi(curve, adopted_phi_u)
    real_area = _trapezoidal_area(truncated)
    if real_area <= 0.0:
        raise ValueError("Area under the moment-curvature curve must be positive.")

    lower_my = max(config.my_lower_ratio * peak.moment, 1e-9)
    upper_my = max(config.my_upper_ratio * peak.moment, lower_my)
    best: dict[str, float | str] | None = None

    for moment_y in _candidate_values(lower_my, upper_my, max(config.search_points, 2)):
        moment_60 = config.stiffness_fraction * moment_y
        try:
            phi_60 = _interpolate_phi_on_ascending_branch(curve, moment_60)
        except ValueError:
            continue
        if phi_60 <= 0.0:
            continue

        effective_stiffness = moment_60 / phi_60
        phi_y = moment_y / effective_stiffness
        if not (0.0 < phi_y < adopted_phi_u):
            continue

        post_yield_stiffness = (adopted_moment_u - moment_y) / (adopted_phi_u - phi_y)
        alpha = post_yield_stiffness / effective_stiffness
        bilinear_area = 0.5 * moment_y * phi_y + 0.5 * (moment_y + adopted_moment_u) * (
            adopted_phi_u - phi_y
        )
        relative_error = (bilinear_area - real_area) / real_area
        absolute_relative_error = abs(relative_error)

        candidate = {
            "Ke": effective_stiffness,
            "My": moment_y,
            "phi_y": phi_y,
            "Kp": post_yield_stiffness,
            "alpha": alpha,
            "A_bilinear": bilinear_area,
            "relative_error": relative_error,
            "absolute_relative_error": absolute_relative_error,
            "phi_60My": phi_60,
            "M_60My": moment_60,
        }
        if best is None or absolute_relative_error < float(best["absolute_relative_error"]):
            best = candidate

    if best is None:
        raise ValueError("No valid bilinearization candidate was found.")

    status = "converged" if float(best["absolute_relative_error"]) <= config.tolerance else "best_effort"
    actual_curve = [{"phi": point.phi, "moment": point.moment} for point in truncated]
    bilinear_curve = [
        {"point": "origin", "phi": 0.0, "moment": 0.0},
        {"point": "yield", "phi": best["phi_y"], "moment": best["My"]},
        {"point": "ultimate", "phi": adopted_phi_u, "moment": adopted_moment_u},
    ]

    return {
        "method": "asce_fema_energy_equivalent_m_phi",
        "status": status,
        "settings": {
            "stiffness_fraction": config.stiffness_fraction,
            "tolerance": config.tolerance,
            "search_points": config.search_points,
            "my_lower_ratio": config.my_lower_ratio,
            "my_upper_ratio": config.my_upper_ratio,
            "post_peak_strength_ratio": post_peak_strength_ratio,
        },
        "peak": {"phi": peak.phi, "moment": peak.moment},
        "ultimate": {"phi": adopted_phi_u, "moment": adopted_moment_u, "mode": ultimate_mode},
        "area": {"A_real": real_area, "A_bilinear": best["A_bilinear"]},
        "parameters": {
            "Ke": best["Ke"],
            "My": best["My"],
            "phi_y": best["phi_y"],
            "Kp": best["Kp"],
            "alpha": best["alpha"],
            "Mu": adopted_moment_u,
            "phi_u": adopted_phi_u,
            "M_60My": best["M_60My"],
            "phi_60My": best["phi_60My"],
            "relative_error": best["relative_error"],
            "absolute_relative_error": best["absolute_relative_error"],
            "ductility_phi": adopted_phi_u / max(float(best["phi_y"]), 1e-15),
        },
        "actual_curve": actual_curve,
        "bilinear_curve": bilinear_curve,
    }

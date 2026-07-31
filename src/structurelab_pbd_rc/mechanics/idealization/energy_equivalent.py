"""Energy-equivalent bilinear idealization for positive monotonic backbones."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class BackbonePoint:
    """One point of a positive monotonic deformation-response backbone."""

    deformation: float
    response: float


@dataclass(frozen=True)
class EnergyEquivalentSettings:
    """Numerical settings shared by ASCE/FEMA-style bilinear idealizations."""

    stiffness_fraction: float = 0.60
    tolerance: float = 0.005
    search_points: int = 5000
    yield_lower_ratio: float = 0.05
    yield_upper_ratio: float = 1.00

    def __post_init__(self) -> None:
        if not 0.0 < self.stiffness_fraction < 1.0:
            raise ValueError("stiffness_fraction must satisfy 0 < value < 1.")
        if self.tolerance < 0.0:
            raise ValueError("tolerance cannot be negative.")
        if self.search_points < 2:
            raise ValueError("search_points must be at least 2.")
        if not 0.0 < self.yield_lower_ratio <= self.yield_upper_ratio:
            raise ValueError(
                "yield ratios must satisfy 0 < yield_lower_ratio <= yield_upper_ratio."
            )


def clean_positive_backbone(points: Iterable[BackbonePoint]) -> list[BackbonePoint]:
    """Return sorted finite positive magnitudes with a unique origin."""

    cleaned: list[BackbonePoint] = []
    for point in points:
        deformation = abs(float(point.deformation))
        response = abs(float(point.response))
        if isfinite(deformation) and isfinite(response):
            cleaned.append(
                BackbonePoint(
                    deformation=deformation,
                    response=response,
                )
            )

    cleaned.sort(key=lambda point: point.deformation)
    if not cleaned:
        raise ValueError("Backbone curve has no valid numeric points.")

    merged: list[BackbonePoint] = []
    for point in cleaned:
        if merged and abs(point.deformation - merged[-1].deformation) <= 1.0e-12:
            if point.response >= merged[-1].response:
                merged[-1] = point
        else:
            merged.append(point)

    if merged[0].deformation > 0.0:
        merged.insert(0, BackbonePoint(deformation=0.0, response=0.0))
    elif abs(merged[0].response) > 1.0e-12:
        merged[0] = BackbonePoint(deformation=0.0, response=0.0)
    return merged


def interpolate_response(points: list[BackbonePoint], deformation: float) -> float:
    """Interpolate the response at one deformation."""

    if deformation <= points[0].deformation:
        return points[0].response
    if deformation >= points[-1].deformation:
        return points[-1].response

    for index in range(1, len(points)):
        left = points[index - 1]
        right = points[index]
        if left.deformation <= deformation <= right.deformation:
            ratio = (deformation - left.deformation) / max(
                right.deformation - left.deformation,
                1.0e-15,
            )
            return left.response + ratio * (right.response - left.response)
    return points[-1].response


def _interpolate_deformation_on_ascending_branch(
    points: list[BackbonePoint],
    response: float,
) -> float:
    """Interpolate deformation for a response on the ascending branch."""

    peak_index = max(range(len(points)), key=lambda index: points[index].response)
    ascending = points[: peak_index + 1]
    for index in range(1, len(ascending)):
        left = ascending[index - 1]
        right = ascending[index]
        lower = min(left.response, right.response)
        upper = max(left.response, right.response)
        if (
            lower <= response <= upper
            and abs(right.response - left.response) > 1.0e-15
        ):
            ratio = (response - left.response) / (
                right.response - left.response
            )
            return left.deformation + ratio * (
                right.deformation - left.deformation
            )
    raise ValueError(f"Response {response} is outside the ascending branch.")


def _truncate_at_deformation(
    points: list[BackbonePoint],
    deformation_u: float,
) -> list[BackbonePoint]:
    """Return a backbone from zero through an interpolated ultimate point."""

    if deformation_u <= 0.0:
        raise ValueError("Ultimate deformation must be positive.")
    if deformation_u > points[-1].deformation + 1.0e-12:
        raise ValueError("Ultimate deformation exceeds the available curve domain.")

    truncated: list[BackbonePoint] = []
    for point in points:
        if point.deformation < deformation_u:
            truncated.append(point)
        elif abs(point.deformation - deformation_u) <= 1.0e-12:
            truncated.append(point)
            break
        else:
            truncated.append(
                BackbonePoint(
                    deformation=deformation_u,
                    response=interpolate_response(points, deformation_u),
                )
            )
            break

    if truncated[-1].deformation < deformation_u:
        truncated.append(
            BackbonePoint(
                deformation=deformation_u,
                response=interpolate_response(points, deformation_u),
            )
        )
    return truncated


def _trapezoidal_area(points: list[BackbonePoint]) -> float:
    area = 0.0
    for index in range(1, len(points)):
        left = points[index - 1]
        right = points[index]
        area += 0.5 * (left.response + right.response) * (
            right.deformation - left.deformation
        )
    return area


def _candidate_values(start: float, stop: float, count: int) -> Iterable[float]:
    step = (stop - start) / (count - 1)
    for index in range(count):
        yield start + index * step


def bilinearize_energy_equivalent(
    points: Iterable[BackbonePoint],
    *,
    deformation_u: float | None = None,
    settings: EnergyEquivalentSettings | None = None,
) -> dict[str, object]:
    """Return a two-segment idealization with effective stiffness and equal area."""

    config = settings or EnergyEquivalentSettings()
    curve = clean_positive_backbone(points)
    peak = max(curve, key=lambda point: point.response)
    adopted_deformation_u = (
        curve[-1].deformation
        if deformation_u is None
        else float(deformation_u)
    )
    truncated = _truncate_at_deformation(curve, adopted_deformation_u)
    adopted_response_u = truncated[-1].response
    real_area = _trapezoidal_area(truncated)
    if real_area <= 0.0:
        raise ValueError("Area under the backbone curve must be positive.")

    lower_yield = max(config.yield_lower_ratio * peak.response, 1.0e-9)
    upper_yield = max(config.yield_upper_ratio * peak.response, lower_yield)
    best: dict[str, float] | None = None

    for yield_response in _candidate_values(
        lower_yield,
        upper_yield,
        config.search_points,
    ):
        fraction_response = config.stiffness_fraction * yield_response
        try:
            fraction_deformation = _interpolate_deformation_on_ascending_branch(
                curve,
                fraction_response,
            )
        except ValueError:
            continue
        if fraction_deformation <= 0.0:
            continue

        effective_stiffness = fraction_response / fraction_deformation
        yield_deformation = yield_response / effective_stiffness
        if not 0.0 < yield_deformation < adopted_deformation_u:
            continue

        post_yield_stiffness = (
            adopted_response_u - yield_response
        ) / (adopted_deformation_u - yield_deformation)
        alpha = post_yield_stiffness / effective_stiffness
        bilinear_area = (
            0.5 * yield_response * yield_deformation
            + 0.5
            * (yield_response + adopted_response_u)
            * (adopted_deformation_u - yield_deformation)
        )
        relative_error = (bilinear_area - real_area) / real_area
        absolute_relative_error = abs(relative_error)
        candidate = {
            "effective_stiffness": effective_stiffness,
            "yield_response": yield_response,
            "yield_deformation": yield_deformation,
            "post_yield_stiffness": post_yield_stiffness,
            "alpha": alpha,
            "bilinear_area": bilinear_area,
            "relative_error": relative_error,
            "absolute_relative_error": absolute_relative_error,
            "fraction_response": fraction_response,
            "fraction_deformation": fraction_deformation,
        }
        if (
            best is None
            or absolute_relative_error < best["absolute_relative_error"]
        ):
            best = candidate

    if best is None:
        raise ValueError("No valid energy-equivalent bilinearization candidate was found.")

    status = (
        "converged"
        if best["absolute_relative_error"] <= config.tolerance
        else "best_effort"
    )
    return {
        "method": "asce_fema_energy_equivalent_bilinear",
        "status": status,
        "settings": {
            "stiffness_fraction": config.stiffness_fraction,
            "tolerance": config.tolerance,
            "search_points": config.search_points,
            "yield_lower_ratio": config.yield_lower_ratio,
            "yield_upper_ratio": config.yield_upper_ratio,
        },
        "peak": {
            "deformation": peak.deformation,
            "response": peak.response,
        },
        "ultimate": {
            "deformation": adopted_deformation_u,
            "response": adopted_response_u,
        },
        "area": {
            "actual": real_area,
            "bilinear": best["bilinear_area"],
        },
        "parameters": {
            **best,
            "ultimate_deformation": adopted_deformation_u,
            "ultimate_response": adopted_response_u,
            "ductility": adopted_deformation_u
            / max(best["yield_deformation"], 1.0e-15),
        },
        "actual_curve": [
            {
                "deformation": point.deformation,
                "response": point.response,
            }
            for point in truncated
        ],
        "bilinear_curve": [
            {"point": "origin", "deformation": 0.0, "response": 0.0},
            {
                "point": "yield",
                "deformation": best["yield_deformation"],
                "response": best["yield_response"],
            },
            {
                "point": "ultimate",
                "deformation": adopted_deformation_u,
                "response": adopted_response_u,
            },
        ],
    }

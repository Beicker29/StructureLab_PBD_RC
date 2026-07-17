"""Response-spectrum equations for seismic hazard characterization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SITE_PROFILES = {"A", "B", "C", "D", "E"}


@dataclass(frozen=True)
class NSR10SpectrumParameters:
    """Transition periods and plateau values for the NSR-10 spectrum."""

    Aa: float
    Av: float
    Fa: float
    Fv: float
    importance_factor: float
    T0: float
    Tc: float
    TL: float
    Sa_plateau: float


@dataclass(frozen=True)
class CCP14SpectrumParameters:
    """Transition periods and spectral ordinates for the CCP-14 spectrum."""

    return_period_years: int
    PGA: float
    Ss: float
    S1: float
    site_profile: str
    Fpga: float
    Fa: float
    Fv: float
    As: float
    SDS: float
    SD1: float
    T0: float
    Ts: float


@dataclass(frozen=True)
class CCP14SiteFactors:
    """Interpolated CCP-14 site factors for one seismic hazard level."""

    site_profile: str
    Fpga: float
    Fa: float
    Fv: float


CCP14_FPGA_PGA_POINTS = (0.10, 0.20, 0.30, 0.40, 0.50)
CCP14_FA_SS_POINTS = (0.25, 0.50, 0.75, 1.00, 1.25)
CCP14_FV_S1_POINTS = (0.10, 0.20, 0.30, 0.40, 0.50)

CCP14_FPGA_TABLE = {
    "A": (0.8, 0.8, 0.8, 0.8, 0.8),
    "B": (1.0, 1.0, 1.0, 1.0, 1.0),
    "C": (1.2, 1.2, 1.1, 1.0, 1.0),
    "D": (1.6, 1.4, 1.2, 1.1, 1.0),
    "E": (2.5, 1.7, 1.2, 0.9, 0.9),
}
CCP14_FA_TABLE = {
    "A": (0.8, 0.8, 0.8, 0.8, 0.8),
    "B": (1.0, 1.0, 1.0, 1.0, 1.0),
    "C": (1.2, 1.2, 1.1, 1.0, 1.0),
    "D": (1.6, 1.4, 1.2, 1.1, 1.0),
    "E": (2.5, 1.7, 1.2, 0.9, 0.9),
}
CCP14_FV_TABLE = {
    "A": (0.8, 0.8, 0.8, 0.8, 0.8),
    "B": (1.0, 1.0, 1.0, 1.0, 1.0),
    "C": (1.7, 1.6, 1.5, 1.4, 1.3),
    "D": (2.4, 2.0, 1.8, 1.6, 1.5),
    "E": (3.5, 3.2, 2.8, 2.4, 2.4),
}


def _require_non_negative(value: float, *, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _require_positive(value: float, *, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def validate_site_profile(profile: str) -> str:
    """Validate supported CCP-14 site profiles."""

    normalized = profile.strip().upper()
    if normalized == "F":
        raise ValueError("CCP-14 site profile F requires note 2 and is not implemented automatically.")
    if normalized not in SITE_PROFILES:
        raise ValueError(f"Unsupported site profile '{profile}'. Expected one of A, B, C, D, E.")
    return normalized


def _linear_interpolate_with_bounds(value: float, points: tuple[float, ...], values: tuple[float, ...]) -> float:
    """Interpolate linearly and use table edge values outside tabulated ranges."""

    if value <= points[0]:
        return values[0]
    if value >= points[-1]:
        return values[-1]
    for index in range(len(points) - 1):
        x0 = points[index]
        x1 = points[index + 1]
        if x0 <= value <= x1:
            y0 = values[index]
            y1 = values[index + 1]
            return y0 + (value - x0) * (y1 - y0) / (x1 - x0)
    return values[-1]


def ccp14_site_factors(*, PGA: float, Ss: float, S1: float, site_profile: str) -> CCP14SiteFactors:
    """Compute CCP-14 Fpga, Fa and Fv by tabular interpolation."""

    _require_non_negative(PGA, name="PGA")
    _require_positive(Ss, name="Ss")
    _require_positive(S1, name="S1")
    profile = validate_site_profile(site_profile)
    return CCP14SiteFactors(
        site_profile=profile,
        Fpga=_linear_interpolate_with_bounds(PGA, CCP14_FPGA_PGA_POINTS, CCP14_FPGA_TABLE[profile]),
        Fa=_linear_interpolate_with_bounds(Ss, CCP14_FA_SS_POINTS, CCP14_FA_TABLE[profile]),
        Fv=_linear_interpolate_with_bounds(S1, CCP14_FV_S1_POINTS, CCP14_FV_TABLE[profile]),
    )


def generate_period_vector(start: float, end: float, step: float) -> list[float]:
    """Generate a stable period vector with inclusive end when it falls on the grid."""

    _require_non_negative(start, name="period_range.start")
    _require_positive(end, name="period_range.end")
    _require_positive(step, name="period_range.step")
    if end < start:
        raise ValueError("period_range.end must be greater than or equal to period_range.start.")

    periods: list[float] = []
    value = start
    tolerance = step * 1e-9
    while value <= end + tolerance:
        periods.append(round(value, 10))
        value += step
    if periods[-1] > end:
        periods[-1] = round(end, 10)
    return periods


def nsr10_transition_parameters(
    *,
    Aa: float,
    Av: float,
    Fa: float,
    Fv: float,
    importance_factor: float,
) -> NSR10SpectrumParameters:
    """Compute NSR-10 transition periods and plateau acceleration."""

    _require_positive(Aa, name="Aa")
    _require_positive(Av, name="Av")
    _require_positive(Fa, name="Fa")
    _require_positive(Fv, name="Fv")
    _require_positive(importance_factor, name="importance_factor")
    ratio = (Av * Fv) / (Aa * Fa)
    return NSR10SpectrumParameters(
        Aa=Aa,
        Av=Av,
        Fa=Fa,
        Fv=Fv,
        importance_factor=importance_factor,
        T0=0.1 * ratio,
        Tc=0.48 * ratio,
        TL=2.4 * Fv,
        Sa_plateau=2.5 * Aa * Fa * importance_factor,
    )


def nsr10_spectral_acceleration(T: float, parameters: NSR10SpectrumParameters) -> float:
    """Evaluate the NSR-10 elastic acceleration spectrum at one period."""

    _require_non_negative(T, name="T")
    if T <= parameters.T0:
        return parameters.Sa_plateau * (0.4 + 0.6 * T / parameters.T0)
    if T <= parameters.Tc:
        return parameters.Sa_plateau
    if T <= parameters.TL:
        return 1.2 * parameters.Av * parameters.Fv * parameters.importance_factor / T
    return 1.2 * parameters.Av * parameters.Fv * parameters.TL * parameters.importance_factor / (T * T)


def nsr10_spectrum(periods: Iterable[float], parameters: NSR10SpectrumParameters) -> list[float]:
    """Evaluate the NSR-10 spectrum for a period vector."""

    return [nsr10_spectral_acceleration(float(period), parameters) for period in periods]


def ccp14_transition_parameters(
    *,
    return_period_years: int,
    PGA: float,
    Ss: float,
    S1: float,
    site_profile: str,
) -> CCP14SpectrumParameters:
    """Compute CCP-14 spectral parameters and interpolated site factors."""

    _require_non_negative(PGA, name="PGA")
    _require_positive(Ss, name="Ss")
    _require_positive(S1, name="S1")
    site_factors = ccp14_site_factors(PGA=PGA, Ss=Ss, S1=S1, site_profile=site_profile)
    As = site_factors.Fpga * PGA
    SDS = site_factors.Fa * Ss
    SD1 = site_factors.Fv * S1
    _require_positive(SDS, name="SDS")
    _require_positive(SD1, name="SD1")
    Ts = SD1 / SDS
    T0 = 0.2 * Ts
    return CCP14SpectrumParameters(
        return_period_years=return_period_years,
        PGA=PGA,
        Ss=Ss,
        S1=S1,
        site_profile=site_factors.site_profile,
        Fpga=site_factors.Fpga,
        Fa=site_factors.Fa,
        Fv=site_factors.Fv,
        As=As,
        SDS=SDS,
        SD1=SD1,
        T0=T0,
        Ts=Ts,
    )


def ccp14_spectral_acceleration(T: float, parameters: CCP14SpectrumParameters) -> float:
    """Evaluate the CCP-14 elastic seismic coefficient Csm at one period."""

    _require_non_negative(T, name="T")
    if T <= parameters.T0:
        return parameters.As + (parameters.SDS - parameters.As) * (T / parameters.T0)
    if T <= parameters.Ts:
        return parameters.SDS
    return parameters.SD1 / T


def ccp14_spectrum(periods: Iterable[float], parameters: CCP14SpectrumParameters) -> list[float]:
    """Evaluate the CCP-14 spectrum for a period vector."""

    return [ccp14_spectral_acceleration(float(period), parameters) for period in periods]

"""Pure equations for the Mander et al. (1988) monotonic envelope."""

from __future__ import annotations

from math import sqrt


def elastic_modulus_mpa(f_co_mpa: float) -> float:
    """Return the initial tangent modulus from Mander et al. Eq. (7)."""

    return 5000.0 * sqrt(f_co_mpa)


def confined_strength_mpa(f_co_mpa: float, f_l_mpa: float) -> float:
    """Return confined strength for equal effective lateral pressures."""

    pressure_ratio = f_l_mpa / f_co_mpa
    return f_co_mpa * (
        -1.254
        + 2.254 * sqrt(1.0 + 7.94 * pressure_ratio)
        - 2.0 * pressure_ratio
    )


def peak_strain(
    epsilon_co: float,
    f_cc_mpa: float,
    f_co_mpa: float,
) -> float:
    """Return the strain at confined compressive strength."""

    return epsilon_co * (1.0 + 5.0 * (f_cc_mpa / f_co_mpa - 1.0))


def secant_modulus_mpa(f_cc_mpa: float, epsilon_cc: float) -> float:
    """Return the secant modulus at the confined peak."""

    return f_cc_mpa / epsilon_cc


def curve_shape_parameter(
    elastic_modulus: float,
    secant_modulus: float,
) -> float:
    """Return the Popovics curve-shape parameter ``r``."""

    return elastic_modulus / (elastic_modulus - secant_modulus)


def simplified_ultimate_strain(
    rho_s: float,
    f_yh_mpa: float,
    epsilon_su_transverse: float,
    f_cc_mpa: float,
) -> float:
    """Return the user-selected simplified hoop-fracture strain."""

    return (
        0.004
        + 1.4
        * rho_s
        * f_yh_mpa
        * epsilon_su_transverse
        / f_cc_mpa
    )


def popovics_stress_mpa(
    strain: float,
    *,
    f_cc_mpa: float,
    epsilon_cc: float,
    r: float,
) -> float:
    """Evaluate the monotonic Popovics stress equation."""

    if strain <= 0.0:
        return 0.0
    x = strain / epsilon_cc
    return f_cc_mpa * x * r / (r - 1.0 + x**r)


def popovics_tangent_mpa(
    strain: float,
    *,
    f_cc_mpa: float,
    epsilon_cc: float,
    r: float,
) -> float:
    """Evaluate the analytical tangent of the Popovics equation."""

    if strain <= 0.0:
        return f_cc_mpa * r / ((r - 1.0) * epsilon_cc)
    x = strain / epsilon_cc
    denominator = r - 1.0 + x**r
    return (
        f_cc_mpa
        * r
        * (r - 1.0)
        * (1.0 - x**r)
        / (epsilon_cc * denominator**2)
    )

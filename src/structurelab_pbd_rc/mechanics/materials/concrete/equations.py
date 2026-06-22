"""Mechanical equations for concrete constitutive models.

These functions are intentionally small and explicit: each one corresponds to
one equation used by a constitutive model or a calculated-parameter report.
"""

from __future__ import annotations

from math import sqrt


def effective_confinement_pressure(
    *,
    ke: float,
    rho_s: float,
    fyh: float,
) -> float:
    """Return effective lateral confinement pressure.

    Equation:
    ``fl = 0.5 * ke * rho_s * fyh``
    """

    return 0.5 * ke * rho_s * fyh


def mander_classic_confined_strength(
    *,
    f_co: float,
    fl: float,
) -> float:
    """Return maximum confined concrete stress for classic Mander.

    Equation:
    ``fcc = f_co * (-1.254 + 2.254*sqrt(1 + 7.94*fl/f_co) - 2*fl/f_co)``
    """

    ratio = fl / f_co if f_co else 0.0
    return f_co * (-1.254 + 2.254 * sqrt(1.0 + 7.94 * ratio) - 2.0 * ratio)


def mander_adjusted_confined_strength(
    *,
    f_co: float,
    fl: float,
) -> float:
    """Return maximum confined concrete stress for adjusted Mander.

    Equation:
    ``fcc = f_co * (1 + 3.5*(fl/f_co)^0.75)``
    """

    ratio = max(fl / f_co, 0.0) if f_co else 0.0
    return f_co * (1.0 + 3.5 * ratio**0.75)


def mander_peak_strain(
    *,
    epsilon_co: float,
    fcc: float,
    f_co: float,
) -> float:
    """Return strain corresponding to maximum confined concrete stress.

    Equation:
    ``epsilon_cc = epsilon_co * (1 + 5*(fcc/f_co - 1))``
    """

    return epsilon_co * (1.0 + 5.0 * (fcc / f_co - 1.0))


def mander_classic_ultimate_strain(
    *,
    rho_s: float,
    fyh: float,
    epsilon_su: float,
    fcc: float,
) -> float:
    """Return ultimate confined concrete strain for classic Mander.

    Equation:
    ``epsilon_cu = 0.004 + 1.4*rho_s*fyh*epsilon_su/fcc``
    """

    return 0.004 + 1.4 * rho_s * fyh * epsilon_su / fcc


def mander_adjusted_transverse_strain(
    *,
    epsilon_su: float,
) -> float:
    """Return adjusted transverse steel strain limit.

    Equation:
    ``epsilon_tst = min(0.6*epsilon_su, 0.06)``
    """

    return min(0.6 * epsilon_su, 0.06)


def mander_adjusted_ultimate_strain(
    *,
    rho_s: float,
    fyh: float,
    epsilon_tst: float,
    fcc: float,
) -> float:
    """Return ultimate confined concrete strain for adjusted Mander.

    Equation:
    ``epsilon_cu = 0.004 + rho_s*fyh*epsilon_tst/fcc``
    """

    return 0.004 + rho_s * fyh * epsilon_tst / fcc


def secant_modulus(
    *,
    stress: float,
    strain: float,
) -> float:
    """Return secant modulus.

    Equation:
    ``Esec = stress / strain``
    """

    return stress / strain


def mander_r_parameter(
    *,
    elastic_modulus: float,
    secant_elastic_modulus: float,
) -> float:
    """Return Mander curve-shape parameter r.

    Equation:
    ``r = Ec / (Ec - Esec)``
    """

    return elastic_modulus / max(elastic_modulus - secant_elastic_modulus, 1e-9)

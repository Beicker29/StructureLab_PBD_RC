"""Ductility and curve metric calculations."""

from structurelab_pbd_rc.core.curves import trapezoid_area


def calculate_ductility(ultimate_strain: float, reference_strain: float) -> float:
    """Calculate strain ductility."""

    if reference_strain <= 0.0:
        return 0.0
    return ultimate_strain / reference_strain


def calculate_curve_metrics(name: str, curve: dict[str, object]) -> dict[str, object]:
    """Calculate basic metrics for a stress-strain curve."""

    strains = [float(value) for value in curve.get("strain", [])]
    stresses = [float(value) for value in curve.get("stress", [])]
    if not strains or not stresses:
        return {
            "model": name,
            "max_stress_mpa": 0.0,
            "strain_at_max_stress": 0.0,
            "ultimate_strain": 0.0,
            "initial_stiffness_mpa": 0.0,
            "strain_ductility": 0.0,
            "toughness_mpa": 0.0,
        }

    max_index = max(range(len(stresses)), key=lambda index: stresses[index])
    max_stress = stresses[max_index]
    strain_at_max = strains[max_index]
    ultimate_strain = strains[-1]
    initial_stiffness = 0.0
    for strain, stress in zip(strains[1:], stresses[1:]):
        if strain > 0.0 and stress > 0.0:
            initial_stiffness = stress / strain
            break
    reference_strain = strain_at_max if "concrete" in name or "mander" in name or "attard" in name else strain_at_max
    return {
        "model": name,
        "max_stress_mpa": max_stress,
        "strain_at_max_stress": strain_at_max,
        "ultimate_strain": ultimate_strain,
        "initial_stiffness_mpa": initial_stiffness,
        "strain_ductility": calculate_ductility(ultimate_strain, reference_strain),
        "toughness_mpa": trapezoid_area(strains, stresses),
    }


def calculate_curve_metrics_table(curves: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Calculate metrics for all named curves."""

    rows = [calculate_curve_metrics(name, curve) for name, curve in curves.items()]
    max_toughness = max((float(row["toughness_mpa"]) for row in rows), default=0.0)
    for row in rows:
        row["relative_energy"] = float(row["toughness_mpa"]) / max_toughness if max_toughness else 0.0
    return rows

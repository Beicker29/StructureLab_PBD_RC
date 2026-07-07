"""Moment-curvature bilinearization tests."""

from __future__ import annotations

from structurelab_pbd_rc.mechanics.sections.moment_curvature import (
    BilinearizationSettings,
    MomentCurvaturePoint,
    bilinearize_moment_curvature,
)


def test_bilinearize_moment_curvature_reports_effective_parameters() -> None:
    points = [
        MomentCurvaturePoint(0.0, 0.0),
        MomentCurvaturePoint(0.001, 80.0),
        MomentCurvaturePoint(0.002, 140.0),
        MomentCurvaturePoint(0.004, 180.0),
        MomentCurvaturePoint(0.008, 165.0),
        MomentCurvaturePoint(0.010, 145.0),
    ]

    result = bilinearize_moment_curvature(
        points,
        phi_u=0.010,
        settings=BilinearizationSettings(search_points=1000, tolerance=0.02),
    )
    parameters = result["parameters"]

    assert result["method"] == "asce_fema_energy_equivalent_m_phi"
    assert result["status"] == "converged"
    assert parameters["Ke"] > 0
    assert parameters["My"] > 0
    assert 0 < parameters["phi_y"] < parameters["phi_u"]
    assert parameters["M_60My"] == 0.60 * parameters["My"]
    assert parameters["absolute_relative_error"] <= 0.02
    assert [point["point"] for point in result["bilinear_curve"]] == ["origin", "yield", "ultimate"]


def test_bilinearize_moment_curvature_uses_post_peak_drop_for_phi_u() -> None:
    points = [
        MomentCurvaturePoint(0.0, 0.0),
        MomentCurvaturePoint(0.001, 100.0),
        MomentCurvaturePoint(0.003, 200.0),
        MomentCurvaturePoint(0.004, 160.0),
        MomentCurvaturePoint(0.006, 120.0),
    ]

    result = bilinearize_moment_curvature(
        points,
        post_peak_strength_ratio=0.80,
        settings=BilinearizationSettings(search_points=800, tolerance=0.05),
    )

    assert result["ultimate"]["mode"] == "first_post_peak_strength_drop"
    assert result["parameters"]["Mu"] == 160.0
    assert result["parameters"]["phi_u"] == 0.004

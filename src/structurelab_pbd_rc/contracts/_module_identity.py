"""Canonical V2 module identities shared by contracts and workflow catalog."""

from __future__ import annotations


V2_MODULE_IDENTITIES: tuple[tuple[str, str, str], ...] = (
    ("00", "project_objectives", "Project & Performance Objectives"),
    ("01", "site_hazard", "Site & Seismic Hazard"),
    ("02", "baseline_model", "Baseline Structural Model"),
    ("03", "material_characterization", "Material Characterization"),
    ("04", "section_component_characterization", "Section & Component Characterization"),
    ("05", "ground_motion", "Ground-Motion Definition"),
    ("06", "nonlinear_model", "Nonlinear Model Assembly & QA"),
    ("07", "nonlinear_analysis", "Nonlinear Analysis"),
    ("08", "demand_performance", "Engineering Demand & Performance Checks"),
    ("09", "collapse_fragility", "Collapse & Fragility"),
    ("10", "damage_loss", "Damage & Loss"),
    ("11", "seismic_risk", "Seismic Risk"),
    ("12", "reporting_iteration", "Reporting & Design Iteration"),
)

MODULE_NUMBER_BY_ID = {module_id: number for number, module_id, _ in V2_MODULE_IDENTITIES}


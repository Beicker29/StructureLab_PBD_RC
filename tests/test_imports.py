"""Import smoke tests for the package skeleton."""

from __future__ import annotations

import importlib


def test_core_package_imports() -> None:
    modules = [
        "structurelab_pbd_rc",
        "structurelab_pbd_rc.core",
        "structurelab_pbd_rc.mechanics.materials.concrete.unconfined",
        "structurelab_pbd_rc.mechanics.materials.steel.reinforcing_bar",
        "structurelab_pbd_rc.mechanics.geometry.sections",
        "structurelab_pbd_rc.mechanics.sections.fiber_section",
        "structurelab_pbd_rc.mechanics.elements.column",
        "structurelab_pbd_rc.mechanics.frames.pushover",
        "structurelab_pbd_rc.mechanics.performance.demand_capacity",
        "structurelab_pbd_rc.reports.report_builder",
        "structurelab_pbd_rc.io.read_config",
    ]
    for module in modules:
        assert importlib.import_module(module)



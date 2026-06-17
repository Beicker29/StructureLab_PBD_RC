"""Import smoke tests for the package skeleton."""

from __future__ import annotations

import importlib


def test_core_package_imports() -> None:
    modules = [
        "structurelab_pbd_rc",
        "structurelab_pbd_rc.core",
        "structurelab_pbd_rc.materials.concrete.unconfined",
        "structurelab_pbd_rc.materials.steel.reinforcing_bar",
        "structurelab_pbd_rc.geometry.sections",
        "structurelab_pbd_rc.sections.fiber_section",
        "structurelab_pbd_rc.elements.column",
        "structurelab_pbd_rc.frames.pushover",
        "structurelab_pbd_rc.performance.demand_capacity",
        "structurelab_pbd_rc.reporting.report_builder",
        "structurelab_pbd_rc.io.read_config",
    ]
    for module in modules:
        assert importlib.import_module(module)


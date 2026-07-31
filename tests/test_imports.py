"""Import smoke tests for the package skeleton."""

from __future__ import annotations

import importlib


def test_core_package_imports() -> None:
    modules = [
        "structurelab_pbd_rc",
        "structurelab_pbd_rc.core",
        "structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic",
        "structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic.mander_1988",
        "structurelab_pbd_rc.mechanics.materials.confined_concrete.cyclic",
        "structurelab_pbd_rc.mechanics.materials.unconfined_concrete.monotonic",
        "structurelab_pbd_rc.mechanics.materials.unconfined_concrete.cyclic",
        "structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic",
        "structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019",
        "structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.cyclic",
        "structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.monotonic",
        "structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.cyclic",
        "structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.monotonic.modified_ramberg_osgood",
        "structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.cyclic.menegotto_pinto",
        "structurelab_pbd_rc.mechanics.geometry.sections",
        "structurelab_pbd_rc.mechanics.hazard.seismic.spectra",
        "structurelab_pbd_rc.mechanics.sections.moment_curvature",
        "structurelab_pbd_rc.reports.report_builder",
        "structurelab_pbd_rc.io.read_config",
        "structurelab_pbd_rc.io.read_xlsx",
        "structurelab_pbd_rc.design.stages.stage_01_hazard",
        "structurelab_pbd_rc.design.stages.stage_02_material_characterization",
        "structurelab_pbd_rc.design.stages.stage_03_section_characterization",
    ]
    for module in modules:
        assert importlib.import_module(module)



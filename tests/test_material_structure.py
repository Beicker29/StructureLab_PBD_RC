"""Tests for the strict Stage 2 input directory layout."""

import json
from pathlib import Path


MATERIALS = {
    "ductile_reinforcing_steel",
    "nonductile_reinforcing_steel",
    "confined_concrete",
    "unconfined_concrete",
}
BEHAVIORS = {"monotonic", "cyclic"}


def test_stage_02_contains_only_the_four_material_directories() -> None:
    root = Path("configs/stage_02")

    assert {path.name for path in root.iterdir() if path.is_dir()} == MATERIALS
    assert not any(path.is_file() for path in root.iterdir())


def test_each_material_contains_only_monotonic_and_cyclic() -> None:
    root = Path("configs/stage_02")

    for material in MATERIALS:
        material_root = root / material
        assert {path.name for path in material_root.iterdir() if path.is_dir()} == BEHAVIORS
        assert not any(path.is_file() for path in material_root.iterdir())


def test_every_stage_02_model_definition_is_independent_json() -> None:
    root = Path("configs/stage_02")
    json_files = sorted(
        path
        for material in MATERIALS
        for path in (root / material).rglob("*.json")
    )

    assert len(json_files) == 4
    assert not list(root.rglob("*.yaml"))
    assert not list(root.rglob("*.yml"))

    model_definitions = []
    for path in json_files:
        config = json.loads(path.read_text(encoding="utf-8"))
        assert path.stem == config["inputs"]["model_id"]
        model_definitions.append(
            (path.parent.parent.name, path.parent.name, config["inputs"]["model_id"])
        )
    assert len(model_definitions) == len(set(model_definitions))


def test_stage_02_documentation_mirrors_material_and_behavior_layout() -> None:
    root = Path("docs/stage_02")

    assert {path.name for path in root.iterdir() if path.is_dir()} == MATERIALS
    for material in MATERIALS:
        material_root = root / material
        assert {path.name for path in material_root.iterdir() if path.is_dir()} == BEHAVIORS

    assert (
        root
        / "ductile_reinforcing_steel/monotonic/Mon_RDM2019/"
        "guia_aplicacion_rdm_2019.pdf"
    ).is_file()
    assert (
        root / "confined_concrete/monotonic/Mon_Mander1988"
    ).is_dir()
    assert (
        root / "nonductile_reinforcing_steel/monotonic/Mon_MRO"
    ).is_dir()
    assert (root / "nonductile_reinforcing_steel/cyclic/Cyc_MP").is_dir()
    assert (
        root
        / "nonductile_reinforcing_steel/monotonic/Mon_MRO/"
        "guia_aplicacion_mon_mro.pdf"
    ).is_file()
    assert (
        root
        / "nonductile_reinforcing_steel/cyclic/Cyc_MP/"
        "guia_aplicacion_cyc_mp.pdf"
    ).is_file()


def test_ductile_steel_references_are_grouped_under_monotonic() -> None:
    root = Path("references/stage_02/ductile_reinforcing_steel")

    assert not (root / "DM").exists()
    assert not (root / "RDM2019").exists()
    assert (root / "monotonic/DM").is_dir()
    assert (root / "monotonic/RDM2019").is_dir()

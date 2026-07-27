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
    json_files = sorted(root.rglob("*.json"))

    assert len(json_files) == 3
    assert not list(root.rglob("*.yaml"))
    assert not list(root.rglob("*.yml"))

    model_definitions = []
    for path in json_files:
        config = json.loads(path.read_text(encoding="utf-8"))
        model_definitions.append(
            (path.parent.parent.name, path.parent.name, config["inputs"]["model_id"])
        )
    assert len(model_definitions) == len(set(model_definitions))

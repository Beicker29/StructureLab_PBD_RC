"""Workflow stub for Taller 5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structurelab_pbd_rc.workflows._base import prepare_workshop_from_config

DEFAULT_CONFIG_PATH = Path("configs/workshops/workshop_05_beam_performance.yaml")


def run(config_path: str | Path = DEFAULT_CONFIG_PATH, output_root: str | Path = "outputs") -> dict[str, Any]:
    """Prepare Taller 5 outputs without implementing beam performance yet."""

    return prepare_workshop_from_config(config_path, output_root=output_root)


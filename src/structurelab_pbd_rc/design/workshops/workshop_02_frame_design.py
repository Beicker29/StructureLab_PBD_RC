"""Workflow stub for Taller 2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structurelab_pbd_rc.design.workshops._base import prepare_workshop_from_config

DEFAULT_CONFIG_PATH = Path("configs/workshops/workshop_02_frame_design.yaml")


def run(config_path: str | Path = DEFAULT_CONFIG_PATH, output_root: str | Path = "outputs") -> dict[str, Any]:
    """Prepare Taller 2 outputs without implementing frame design yet."""

    return prepare_workshop_from_config(config_path, output_root=output_root)



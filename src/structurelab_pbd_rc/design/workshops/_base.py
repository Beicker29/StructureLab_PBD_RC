"""Shared helpers for workshop design flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structurelab_pbd_rc.io.paths import ensure_workshop_output_dirs
from structurelab_pbd_rc.io.read_config import load_workshop_config


def prepare_workshop_from_config(
    config_path: str | Path,
    output_root: str | Path = "outputs",
    *,
    required_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Load a workshop config and prepare its output directories."""

    config = load_workshop_config(config_path, required_keys=required_keys)
    workshop_id = str(config.get("workshop_id", Path(config_path).stem))
    output_dirs = ensure_workshop_output_dirs(workshop_id, output_root=output_root)
    return {
        "workshop_id": workshop_id,
        "config": config,
        "output_dirs": output_dirs,
        "status": "prepared",
    }

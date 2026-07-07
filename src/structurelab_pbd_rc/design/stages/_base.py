"""Shared helpers for stage design flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structurelab_pbd_rc.io.paths import ensure_stage_output_dirs
from structurelab_pbd_rc.io.read_config import load_stage_config


def prepare_stage_from_config(
    config_path: str | Path,
    output_root: str | Path = "outputs",
    *,
    required_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Load a stage config and prepare its output directories."""

    config = load_stage_config(config_path, required_keys=required_keys)
    stage_id = str(config.get("stage_id", Path(config_path).stem))
    output_dirs = ensure_stage_output_dirs(stage_id, output_root=output_root)
    return {
        "stage_id": stage_id,
        "config": config,
        "output_dirs": output_dirs,
        "status": "prepared",
    }

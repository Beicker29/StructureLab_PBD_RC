"""Configuration readers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file as a dictionary."""

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration file must contain a mapping: {config_path}")
    return data


def load_stage_config(path: str | Path, *, required_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    """Load a stage YAML file and optionally validate top-level keys."""

    config = load_yaml_config(path)
    require_keys(config, ("stage_id", "title", *required_keys), context=f"stage config {path}")
    return config

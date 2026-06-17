"""Serialization helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def to_json_safe(value: Any) -> Any:
    """Convert common project objects to JSON-safe values."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]
    return value


"""Shared validation and serialization helpers for V2 contracts."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import fields
from enum import Enum
from typing import Any, TypeVar

from structurelab_pbd_rc.core.exceptions import ContractError, SchemaVersionError


V2_SCHEMA_VERSION = "2"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SEMANTIC_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_schema_version(value: object) -> str:
    version = str(value)
    if version != V2_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"Unsupported schema_version {version!r}; expected {V2_SCHEMA_VERSION!r}."
        )
    return version


def validate_identifier(value: object, *, name: str, semantic: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} must be a non-empty string.")
    pattern = _SEMANTIC_IDENTIFIER if semantic else _IDENTIFIER
    if pattern.fullmatch(value) is None:
        raise ContractError(f"{name} has invalid identifier syntax: {value!r}.")
    return value


def validate_non_empty(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string.")
    return value


def validate_positive(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise ContractError(f"{name} must be a finite positive number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{name} must be a finite positive number.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ContractError(f"{name} must be a finite positive number.")
    return number


def ensure_unique_ids(values: Iterable[str], *, name: str) -> None:
    seen: dict[str, str] = {}
    for value in values:
        key = value.casefold()
        if key in seen:
            raise ContractError(
                f"Duplicate {name} {value!r}; it conflicts with {seen[key]!r}."
            )
        seen[key] = value


def ensure_mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be a mapping.")
    return value


def copy_json_mapping(value: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    copied = deepcopy(dict(value))
    try:
        encoded = json.dumps(copied, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{name} must contain only finite JSON-compatible values.") from exc
    return json.loads(encoded)


def reject_unknown_fields(data: Mapping[str, Any], allowed: set[str], *, name: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractError(f"Unknown fields in {name}: {', '.join(unknown)}.")


def dataclass_field_names(dataclass_type: type[Any]) -> set[str]:
    """Return constructor field names, excluding ``ClassVar`` declarations."""

    return {item.name for item in fields(dataclass_type)}


EnumT = TypeVar("EnumT", bound=Enum)


def parse_enum(enum_type: type[EnumT], value: object, *, name: str) -> EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(item.value) for item in enum_type)
        raise ContractError(f"{name} must be one of [{allowed}].") from exc


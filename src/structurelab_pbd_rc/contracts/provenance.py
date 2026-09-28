"""Stable process provenance used to verify V2 artifact reuse."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from structurelab_pbd_rc.contracts._common import (
    copy_json_mapping,
    dataclass_field_names,
    ensure_mapping,
    reject_unknown_fields,
    validate_identifier,
    validate_non_empty,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts._module_identity import MODULE_NUMBER_BY_ID
from structurelab_pbd_rc.core.exceptions import ContractError


def _validate_hash_mapping(value: Mapping[str, str], *, name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be a mapping of identifiers to SHA-256 hashes.")
    validated: dict[str, str] = {}
    for key, digest in value.items():
        validate_identifier(key, name=f"{name} key")
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in digest
        ):
            raise ContractError(f"{name}[{key!r}] must be a SHA-256 hash.")
        validated[key] = digest.lower()
    return dict(sorted(validated.items()))


def _validate_string_mapping(value: Mapping[str, str], *, name: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str)
        and key.strip()
        and isinstance(item, str)
        and item.strip()
        for key, item in value.items()
    ):
        raise ContractError(f"{name} must be a string-to-string mapping.")
    return dict(sorted(value.items()))


@dataclass(frozen=True)
class ProcessProvenance:
    """Non-volatile inputs that identify how an artifact was produced."""

    schema_version: str
    module_id: str
    implementation_version: str
    resolved_configuration: dict[str, Any]
    input_hashes: dict[str, str] = field(default_factory=dict)
    dependency_hashes: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    sign_conventions: dict[str, str] = field(default_factory=dict)
    backend_version: str | None = None

    def __post_init__(self) -> None:
        validate_schema_version(self.schema_version)
        validate_identifier(self.module_id, name="module_id", semantic=True)
        if self.module_id not in MODULE_NUMBER_BY_ID:
            raise ContractError(f"Unknown V2 module_id {self.module_id!r}.")
        validate_non_empty(self.implementation_version, name="implementation_version")
        object.__setattr__(
            self,
            "resolved_configuration",
            copy_json_mapping(
                self.resolved_configuration,
                name="ProcessProvenance.resolved_configuration",
            ),
        )
        object.__setattr__(
            self,
            "input_hashes",
            _validate_hash_mapping(self.input_hashes, name="input_hashes"),
        )
        object.__setattr__(
            self,
            "dependency_hashes",
            _validate_hash_mapping(self.dependency_hashes, name="dependency_hashes"),
        )
        object.__setattr__(
            self,
            "units",
            _validate_string_mapping(self.units, name="units"),
        )
        object.__setattr__(
            self,
            "sign_conventions",
            _validate_string_mapping(self.sign_conventions, name="sign_conventions"),
        )
        if self.backend_version is not None:
            validate_non_empty(self.backend_version, name="backend_version")

    @property
    def signature(self) -> str:
        encoded = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "module_id": self.module_id,
            "implementation_version": self.implementation_version,
            "resolved_configuration": copy_json_mapping(
                self.resolved_configuration,
                name="ProcessProvenance.resolved_configuration",
            ),
            "input_hashes": dict(self.input_hashes),
            "dependency_hashes": dict(self.dependency_hashes),
            "units": dict(self.units),
            "sign_conventions": dict(self.sign_conventions),
            "backend_version": self.backend_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessProvenance":
        mapping = ensure_mapping(data, name="ProcessProvenance")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="ProcessProvenance")
        return cls(**dict(mapping))

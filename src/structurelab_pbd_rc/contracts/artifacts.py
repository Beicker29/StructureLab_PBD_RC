"""Artifact manifest contracts and dependency integrity checks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, ClassVar, Iterable

from structurelab_pbd_rc.contracts._common import (
    V2_SCHEMA_VERSION,
    copy_json_mapping,
    dataclass_field_names,
    ensure_mapping,
    ensure_unique_ids,
    reject_unknown_fields,
    validate_identifier,
    validate_non_empty,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts._module_identity import MODULE_NUMBER_BY_ID
from structurelab_pbd_rc.core.exceptions import ContractError, DependencyError
from structurelab_pbd_rc.contracts.provenance import ProcessProvenance


def _validate_sha256(value: str, *, name: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdefABCDEF" for character in value):
        raise ContractError(f"{name} must be a 64-character hexadecimal SHA-256 digest.")
    return value.lower()


@dataclass(frozen=True)
class ArtifactDependency:
    artifact_id: str
    sha256: str

    def __post_init__(self) -> None:
        validate_identifier(self.artifact_id, name="dependency.artifact_id")
        object.__setattr__(
            self, "sha256", _validate_sha256(self.sha256, name="dependency.sha256")
        )

    def to_dict(self) -> dict[str, str]:
        return {"artifact_id": self.artifact_id, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactDependency":
        reject_unknown_fields(data, {"artifact_id", "sha256"}, name="ArtifactDependency")
        return cls(**data)


@dataclass(frozen=True)
class ArtifactManifest:
    """Traceable identity and provenance for a single V2 artifact."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    artifact_id: str
    artifact_type: str
    module_id: str
    stage_number: str
    producer: str
    uri: str
    sha256: str
    units: dict[str, str] = field(default_factory=dict)
    sign_conventions: dict[str, str] = field(default_factory=dict)
    axes: dict[str, str] = field(default_factory=dict)
    dependencies: tuple[ArtifactDependency, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProcessProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        validate_schema_version(self.schema_version)
        validate_identifier(self.artifact_id, name="artifact_id")
        validate_identifier(self.artifact_type, name="artifact_type", semantic=True)
        validate_identifier(self.module_id, name="module_id", semantic=True)
        expected_number = MODULE_NUMBER_BY_ID.get(self.module_id)
        if expected_number is None:
            raise ContractError(f"Unknown V2 module_id {self.module_id!r}.")
        if self.stage_number != expected_number:
            raise ContractError(
                f"module_id {self.module_id!r} requires stage_number {expected_number!r}, "
                f"not {self.stage_number!r}."
            )
        validate_non_empty(self.producer, name="producer")
        _validate_relative_uri(self.uri)
        object.__setattr__(self, "sha256", _validate_sha256(self.sha256, name="sha256"))
        for name in ("units", "sign_conventions", "axes"):
            mapping = getattr(self, name)
            if not isinstance(mapping, Mapping) or not all(
                isinstance(key, str) and isinstance(value, str)
                and key.strip() and value.strip()
                for key, value in mapping.items()
            ):
                raise ContractError(f"{name} must be a string-to-string mapping.")
            object.__setattr__(self, name, dict(mapping))
        ensure_unique_ids(
            (item.artifact_id for item in self.dependencies),
            name="artifact dependency",
        )
        if any(item.artifact_id.casefold() == self.artifact_id.casefold() for item in self.dependencies):
            raise ContractError(f"Artifact {self.artifact_id!r} cannot depend on itself.")
        if self.provenance is not None:
            if not isinstance(self.provenance, ProcessProvenance):
                raise ContractError("provenance must be a ProcessProvenance instance.")
            if (
                self.provenance.schema_version != self.schema_version
                or self.provenance.module_id != self.module_id
            ):
                raise ContractError(
                    "Artifact provenance must match its schema_version and module_id."
                )
        object.__setattr__(
            self, "metadata", copy_json_mapping(self.metadata, name="ArtifactManifest.metadata")
        )

    @property
    def content_hash(self) -> str:
        """Explicit name for the published byte hash, distinct from provenance."""

        return self.sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "module_id": self.module_id,
            "stage_number": self.stage_number,
            "producer": self.producer,
            "uri": self.uri,
            "sha256": self.sha256,
            "units": dict(self.units),
            "sign_conventions": dict(self.sign_conventions),
            "axes": dict(self.axes),
            "dependencies": [item.to_dict() for item in self.dependencies],
            "metadata": copy_json_mapping(self.metadata, name="ArtifactManifest.metadata"),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactManifest":
        mapping = ensure_mapping(data, name="ArtifactManifest")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="ArtifactManifest")
        values = dict(mapping)
        validate_schema_version(values.get("schema_version"))
        values["dependencies"] = tuple(
            ArtifactDependency.from_dict(dict(ensure_mapping(item, name="artifact dependency")))
            for item in values.get("dependencies", ())
        )
        provenance = values.get("provenance")
        values["provenance"] = (
            ProcessProvenance.from_dict(
                dict(ensure_mapping(provenance, name="artifact provenance"))
            )
            if provenance is not None
            else None
        )
        return cls(**values)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "ArtifactManifest":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("ArtifactManifest JSON is invalid.") from exc
        return cls.from_dict(dict(ensure_mapping(data, name="ArtifactManifest")))


def _validate_relative_uri(uri: str) -> None:
    validate_non_empty(uri, name="uri")
    if "\\" in uri or "://" in uri:
        raise ContractError("artifact uri must be a relative POSIX URI.")
    path = PurePosixPath(uri)
    if path.is_absolute() or ".." in path.parts or uri.startswith("/"):
        raise ContractError("artifact uri must remain within the run root.")


def validate_artifact_dependencies(artifacts: Iterable[ArtifactManifest]) -> None:
    """Validate unique artifact IDs and all declared dependency ID/hash pairs."""

    values = tuple(artifacts)
    ensure_unique_ids((item.artifact_id for item in values), name="artifact_id")
    by_id = {item.artifact_id.casefold(): item for item in values}
    for artifact in values:
        for dependency in artifact.dependencies:
            resolved = by_id.get(dependency.artifact_id.casefold())
            if resolved is None:
                raise DependencyError(
                    f"Artifact {artifact.artifact_id!r} has missing dependency "
                    f"{dependency.artifact_id!r}."
                )
            if resolved.sha256 != dependency.sha256:
                raise DependencyError(
                    f"Artifact {artifact.artifact_id!r} dependency "
                    f"{dependency.artifact_id!r} has a SHA-256 mismatch."
                )


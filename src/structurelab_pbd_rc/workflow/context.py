"""Run context contract for an isolated V2 execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from structurelab_pbd_rc.contracts._common import (
    V2_SCHEMA_VERSION,
    copy_json_mapping,
    dataclass_field_names,
    ensure_mapping,
    reject_unknown_fields,
    validate_identifier,
    validate_non_empty,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts.project import ProjectSpec
from structurelab_pbd_rc.core.exceptions import ContractError


@dataclass(frozen=True)
class RunContext:
    """Resolved, serializable identity and environment of one V2 run."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    run_id: str
    project_id: str
    design_revision: str
    case_id: str
    project_root: str
    code_version: str
    environment: dict[str, Any]
    resolved_configuration: dict[str, Any]
    publication_policy: str = "atomic"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_schema_version(self.schema_version)
        for name in ("run_id", "project_id", "design_revision", "case_id"):
            validate_identifier(getattr(self, name), name=name)
        validate_non_empty(self.project_root, name="project_root")
        if not Path(self.project_root).is_absolute():
            raise ContractError("project_root must be an explicit absolute path.")
        validate_non_empty(self.code_version, name="code_version")
        validate_identifier(self.publication_policy, name="publication_policy", semantic=True)
        object.__setattr__(
            self,
            "environment",
            copy_json_mapping(self.environment, name="RunContext.environment"),
        )
        object.__setattr__(
            self,
            "resolved_configuration",
            copy_json_mapping(
                self.resolved_configuration,
                name="RunContext.resolved_configuration",
            ),
        )
        object.__setattr__(
            self, "metadata", copy_json_mapping(self.metadata, name="RunContext.metadata")
        )

    @classmethod
    def from_project_spec(
        cls,
        project: ProjectSpec,
        *,
        run_id: str,
        project_root: str | Path,
        code_version: str,
        environment: dict[str, Any] | None = None,
        resolved_configuration: dict[str, Any] | None = None,
        publication_policy: str = "atomic",
    ) -> "RunContext":
        return cls(
            schema_version=project.schema_version,
            run_id=run_id,
            project_id=project.project_id,
            design_revision=project.design_revision,
            case_id=project.case_id,
            project_root=str(Path(project_root).resolve()),
            code_version=code_version,
            environment=environment or {},
            resolved_configuration=resolved_configuration or project.to_dict(),
            publication_policy=publication_policy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "design_revision": self.design_revision,
            "case_id": self.case_id,
            "project_root": self.project_root,
            "code_version": self.code_version,
            "environment": copy_json_mapping(self.environment, name="RunContext.environment"),
            "resolved_configuration": copy_json_mapping(
                self.resolved_configuration,
                name="RunContext.resolved_configuration",
            ),
            "publication_policy": self.publication_policy,
            "metadata": copy_json_mapping(self.metadata, name="RunContext.metadata"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunContext":
        mapping = ensure_mapping(data, name="RunContext")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="RunContext")
        validate_schema_version(mapping.get("schema_version"))
        return cls(**dict(mapping))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "RunContext":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("RunContext JSON is invalid.") from exc
        return cls.from_dict(dict(ensure_mapping(data, name="RunContext")))


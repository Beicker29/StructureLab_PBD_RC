"""Stage result contract with independent execution and assessment states."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from structurelab_pbd_rc.contracts._common import (
    V2_SCHEMA_VERSION,
    copy_json_mapping,
    dataclass_field_names,
    ensure_mapping,
    parse_enum,
    reject_unknown_fields,
    validate_identifier,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts._module_identity import MODULE_NUMBER_BY_ID
from structurelab_pbd_rc.contracts.artifacts import ArtifactManifest
from structurelab_pbd_rc.core.exceptions import ContractError


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_IMPLEMENTED = "not_implemented"


class NumericalQualityStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    NOT_APPLICABLE = "not_applicable"
    CONVERGED = "converged"
    BEST_EFFORT = "best_effort"
    NOT_CONVERGED = "not_converged"


class ApplicabilityStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"


class PerformanceAcceptanceStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StageMessage:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.code, name="message.code")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ContractError("message.message must be a non-empty string.")
        object.__setattr__(
            self, "details", copy_json_mapping(self.details, name="message.details")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": copy_json_mapping(self.details, name="message.details"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageMessage":
        reject_unknown_fields(data, {"code", "message", "details"}, name="StageMessage")
        return cls(**data)


@dataclass(frozen=True)
class StageResult:
    """Outcome of one module without conflating completion and acceptance."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    module_id: str
    stage_number: str
    execution_status: ExecutionStatus
    numerical_quality: NumericalQualityStatus
    applicability: ApplicabilityStatus
    performance_acceptance: PerformanceAcceptanceStatus
    artifacts: tuple[ArtifactManifest, ...] = ()
    warnings: tuple[StageMessage, ...] = ()
    errors: tuple[StageMessage, ...] = ()
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))
        validate_schema_version(self.schema_version)
        validate_identifier(self.module_id, name="module_id", semantic=True)
        expected_number = MODULE_NUMBER_BY_ID.get(self.module_id)
        if expected_number is None or self.stage_number != expected_number:
            raise ContractError(
                f"Invalid V2 module identity {self.stage_number!r}/{self.module_id!r}."
            )
        object.__setattr__(
            self,
            "execution_status",
            parse_enum(ExecutionStatus, self.execution_status, name="execution_status"),
        )
        object.__setattr__(
            self,
            "numerical_quality",
            parse_enum(NumericalQualityStatus, self.numerical_quality, name="numerical_quality"),
        )
        object.__setattr__(
            self,
            "applicability",
            parse_enum(ApplicabilityStatus, self.applicability, name="applicability"),
        )
        object.__setattr__(
            self,
            "performance_acceptance",
            parse_enum(
                PerformanceAcceptanceStatus,
                self.performance_acceptance,
                name="performance_acceptance",
            ),
        )
        try:
            duration = float(self.duration_seconds)
        except (TypeError, ValueError) as exc:
            raise ContractError("duration_seconds must be a nonnegative finite number.") from exc
        if duration < 0 or duration == float("inf") or duration != duration:
            raise ContractError("duration_seconds must be a nonnegative finite number.")
        object.__setattr__(self, "duration_seconds", duration)
        artifact_ids = [item.artifact_id.casefold() for item in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ContractError("StageResult contains duplicate artifact IDs.")
        if any(item.module_id != self.module_id for item in self.artifacts):
            raise ContractError("Every StageResult artifact must be produced by the same module.")
        if self.performance_acceptance is PerformanceAcceptanceStatus.ACCEPTED:
            if self.execution_status is not ExecutionStatus.COMPLETED:
                raise ContractError("Performance cannot be accepted when execution is not completed.")
            if self.applicability is not ApplicabilityStatus.APPLICABLE:
                raise ContractError("Performance acceptance requires an applicable result.")
            if self.numerical_quality is NumericalQualityStatus.NOT_CONVERGED:
                raise ContractError("A non-converged result cannot be accepted.")
        object.__setattr__(
            self, "metadata", copy_json_mapping(self.metadata, name="StageResult.metadata")
        )

    @property
    def completed(self) -> bool:
        return self.execution_status is ExecutionStatus.COMPLETED

    @property
    def accepted(self) -> bool:
        return self.performance_acceptance is PerformanceAcceptanceStatus.ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "module_id": self.module_id,
            "stage_number": self.stage_number,
            "execution_status": self.execution_status.value,
            "numerical_quality": self.numerical_quality.value,
            "applicability": self.applicability.value,
            "performance_acceptance": self.performance_acceptance.value,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "warnings": [item.to_dict() for item in self.warnings],
            "errors": [item.to_dict() for item in self.errors],
            "duration_seconds": self.duration_seconds,
            "metadata": copy_json_mapping(self.metadata, name="StageResult.metadata"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageResult":
        mapping = ensure_mapping(data, name="StageResult")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="StageResult")
        values = dict(mapping)
        validate_schema_version(values.get("schema_version"))
        values["artifacts"] = tuple(
            ArtifactManifest.from_dict(dict(ensure_mapping(item, name="artifact")))
            for item in values.get("artifacts", ())
        )
        for name in ("warnings", "errors"):
            values[name] = tuple(
                StageMessage.from_dict(dict(ensure_mapping(item, name=name)))
                for item in values.get(name, ())
            )
        return cls(**values)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "StageResult":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("StageResult JSON is invalid.") from exc
        return cls.from_dict(dict(ensure_mapping(data, name="StageResult")))


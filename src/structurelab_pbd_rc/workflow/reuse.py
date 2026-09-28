"""Verified, manifest-addressed reuse of immutable V2 publications."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ArtifactManifest,
    ExecutionStatus,
    NumericalQualityStatus,
    ProcessProvenance,
    StageResult,
    validate_artifact_dependencies,
)
from structurelab_pbd_rc.contracts._common import validate_identifier, validate_schema_version
from structurelab_pbd_rc.core.exceptions import ContractError
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.registry import HandlerRegistration


_VOLATILE_CONFIGURATION_KEYS = {
    "completed_at",
    "created_at",
    "output_root",
    "project_root",
    "run_id",
    "started_at",
    "timestamp",
    "updated_at",
}


def stable_configuration(value: Any) -> Any:
    """Remove operational fields that cannot affect scientific content."""

    if isinstance(value, Mapping):
        return {
            str(key): stable_configuration(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).casefold() not in _VOLATILE_CONFIGURATION_KEYS
            and not (
                isinstance(item, str)
                and (
                    PurePosixPath(item).is_absolute()
                    or PureWindowsPath(item).is_absolute()
                )
            )
        }
    if isinstance(value, list):
        return [stable_configuration(item) for item in value]
    return value


def module_content_hash(artifacts: tuple[ArtifactManifest, ...]) -> str:
    """Hash a module's declared content identities, independently of run paths."""

    if not artifacts:
        raise ContractError("A reusable module must publish at least one artifact.")
    payload = {
        artifact.artifact_id: artifact.content_hash
        for artifact in sorted(artifacts, key=lambda item: item.artifact_id)
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def expected_provenance(
    context: RunContext,
    module_id: str,
    registration: HandlerRegistration,
    dependency_hashes: Mapping[str, str],
) -> ProcessProvenance | None:
    """Build expected provenance, or return None when evidence is insufficient."""

    if not registration.reuse_allowed or registration.implementation_version is None:
        return None
    all_input_hashes = context.metadata.get("input_hashes", {})
    if not isinstance(all_input_hashes, Mapping):
        return None
    raw_input_hashes = all_input_hashes.get(module_id, {})
    if not isinstance(raw_input_hashes, Mapping):
        return None
    if any(item not in raw_input_hashes for item in registration.required_input_ids):
        return None
    configuration: Any = context.resolved_configuration
    if registration.configuration_path is not None:
        for key in registration.configuration_path:
            if not isinstance(configuration, Mapping) or key not in configuration:
                return None
            configuration = configuration[key]
        if not isinstance(configuration, Mapping):
            return None
    try:
        return ProcessProvenance(
            schema_version=context.schema_version,
            module_id=module_id,
            implementation_version=registration.implementation_version,
            resolved_configuration=stable_configuration(configuration),
            input_hashes=dict(raw_input_hashes),
            dependency_hashes=dict(dependency_hashes),
            units=dict(registration.units),
            sign_conventions=dict(registration.sign_conventions),
            backend_version=registration.backend_version,
        )
    except ContractError:
        return None


@dataclass(frozen=True)
class ReuseReason:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.code, name="reuse reason code", semantic=True)
        if not isinstance(self.message, str) or not self.message.strip():
            raise ContractError("Reuse reason message must be non-empty.")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class PublishedRunReference:
    """Explicit pointer to one immutable run manifest; no discovery is performed."""

    project_id: str
    design_revision: str
    case_id: str
    run_id: str
    manifest_sha256: str
    priority: int = 0

    def __post_init__(self) -> None:
        for name in ("project_id", "design_revision", "case_id", "run_id"):
            validate_identifier(getattr(self, name), name=name)
        if len(self.manifest_sha256) != 64 or any(
            item not in "0123456789abcdefABCDEF" for item in self.manifest_sha256
        ):
            raise ContractError("manifest_sha256 must be a SHA-256 hash.")
        object.__setattr__(self, "manifest_sha256", self.manifest_sha256.lower())
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ContractError("Published run priority must be an integer.")

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return self.project_id, self.design_revision, self.case_id, self.run_id


class PublishedRunIndex:
    """Caller-supplied deterministic candidate list for verified reuse."""

    def __init__(self, references: tuple[PublishedRunReference, ...] = ()) -> None:
        self.references = tuple(references)
        identities = [item.identity for item in self.references]
        if len(identities) != len(set(identities)):
            raise ContractError("PublishedRunIndex contains a duplicate run identity.")

    def candidates_for(self, context: RunContext) -> tuple[PublishedRunReference, ...]:
        identity = (context.project_id, context.design_revision, context.case_id)
        candidates = (
            item
            for item in self.references
            if (item.project_id, item.design_revision, item.case_id) == identity
            and item.run_id != context.run_id
        )
        return tuple(sorted(candidates, key=lambda item: (item.priority, item.run_id)))


@dataclass(frozen=True)
class ReuseSelection:
    reference: PublishedRunReference
    result: StageResult
    artifact_bytes: Mapping[str, bytes]
    module_content_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_bytes",
            MappingProxyType(dict(self.artifact_bytes)),
        )


@dataclass(frozen=True)
class ReuseCheck:
    selection: ReuseSelection | None
    reason: ReuseReason


@dataclass(frozen=True)
class _PublishedSnapshot:
    reference: PublishedRunReference
    results: Mapping[str, StageResult]
    artifact_bytes: Mapping[str, bytes]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_snapshot(
    output_root: Path,
    reference: PublishedRunReference,
) -> tuple[_PublishedSnapshot | None, ReuseReason | None]:
    root = output_root.resolve().joinpath(
        "v2",
        reference.project_id,
        reference.design_revision,
        reference.case_id,
        reference.run_id,
    )
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return None, ReuseReason(
            "manifest_missing",
            "The referenced published run has no manifest.json.",
            {"run_id": reference.run_id},
        )
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        return None, ReuseReason("manifest_unreadable", str(exc))
    if _sha256_bytes(manifest_bytes) != reference.manifest_sha256:
        return None, ReuseReason(
            "manifest_hash_mismatch",
            "The explicit run manifest hash does not match its published bytes.",
            {"run_id": reference.run_id},
        )
    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
        validate_schema_version(payload.get("schema_version"))
        if payload.get("publication_status") != "complete":
            raise ContractError("publication_status is not complete")
        manifest_context = RunContext.from_dict(payload["run_context"])
        if (
            manifest_context.project_id,
            manifest_context.design_revision,
            manifest_context.case_id,
            manifest_context.run_id,
        ) != reference.identity:
            raise ContractError("run context identity does not match the reference")
        results = tuple(StageResult.from_dict(item) for item in payload["stage_results"])
        if not results or any(
            result.execution_status is not ExecutionStatus.COMPLETED
            for result in results
        ):
            raise ContractError("stage results are absent or incomplete")
        if len({item.module_id for item in results}) != len(results):
            raise ContractError("stage results contain duplicate module IDs")
        artifacts = tuple(
            artifact for result in results for artifact in result.artifacts
        )
        declared = tuple(
            ArtifactManifest.from_dict(item) for item in payload["artifacts"]
        )
        if [item.to_dict() for item in declared] != [
            item.to_dict() for item in artifacts
        ]:
            raise ContractError("run-level and stage artifact declarations differ")
        validate_artifact_dependencies(artifacts)
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        return None, ReuseReason(
            "manifest_incomplete",
            f"The referenced run manifest is incomplete or incompatible: {exc}",
            {"run_id": reference.run_id},
        )

    artifact_bytes: dict[str, bytes] = {}
    for artifact in artifacts:
        if artifact.metadata.get("corrupt") or artifact.metadata.get("incomplete"):
            return None, ReuseReason(
                "artifact_marked_invalid",
                f"Artifact {artifact.artifact_id!r} is marked corrupt or incomplete.",
            )
        relative = PurePosixPath(artifact.uri)
        path = root.joinpath(*relative.parts)
        if not path.is_file():
            return None, ReuseReason(
                "artifact_missing",
                f"Published artifact {artifact.artifact_id!r} is absent.",
            )
        try:
            content = path.read_bytes()
        except OSError as exc:
            return None, ReuseReason("artifact_unreadable", str(exc))
        if _sha256_bytes(content) != artifact.content_hash:
            return None, ReuseReason(
                "content_hash_mismatch",
                f"Published artifact {artifact.artifact_id!r} failed content verification.",
            )
        artifact_bytes[artifact.uri] = content
    return (
        _PublishedSnapshot(
            reference,
            MappingProxyType({item.module_id: item for item in results}),
            MappingProxyType(artifact_bytes),
        ),
        None,
    )


def _quality_allows_reuse(
    result: StageResult,
    *,
    allow_best_effort: bool = False,
) -> bool:
    allowed_quality = {
        NumericalQualityStatus.CONVERGED,
        NumericalQualityStatus.NOT_APPLICABLE,
    }
    if allow_best_effort:
        allowed_quality.add(NumericalQualityStatus.BEST_EFFORT)
    return (
        result.numerical_quality in allowed_quality
        and result.applicability
        in {ApplicabilityStatus.APPLICABLE, ApplicabilityStatus.NOT_APPLICABLE}
        and not result.metadata.get("corrupt")
        and not result.metadata.get("incomplete")
    )


def select_reusable_module(
    *,
    output_root: Path,
    references: tuple[PublishedRunReference, ...],
    module_id: str,
    expected: ProcessProvenance | None,
    allow_best_effort: bool = False,
) -> ReuseCheck:
    """Choose the first valid explicit candidate in deterministic priority order."""

    if expected is None:
        return ReuseCheck(
            None,
            ReuseReason(
                "provenance_insufficient",
                "Expected process provenance is incomplete; reuse is conservative.",
            ),
        )
    failures: list[ReuseReason] = []
    for reference in references:
        snapshot, load_failure = _load_snapshot(output_root, reference)
        if load_failure is not None:
            failures.append(load_failure)
            continue
        assert snapshot is not None
        result = snapshot.results.get(module_id)
        if result is None:
            failures.append(
                ReuseReason(
                    "module_absent",
                    f"Run {reference.run_id!r} has no result for {module_id!r}.",
                )
            )
            continue
        if not result.artifacts:
            failures.append(
                ReuseReason(
                    "artifact_evidence_absent",
                    "A result without published artifacts cannot be reused.",
                )
            )
            continue
        if not _quality_allows_reuse(
            result,
            allow_best_effort=allow_best_effort,
        ):
            failures.append(
                ReuseReason(
                    "qa_policy_rejected",
                    "The candidate does not satisfy the conservative QA reuse policy.",
                )
            )
            continue
        signatures = {
            item.provenance.signature
            for item in result.artifacts
            if item.provenance is not None
        }
        if len(signatures) != 1 or any(
            item.provenance is None for item in result.artifacts
        ):
            failures.append(
                ReuseReason(
                    "provenance_absent",
                    "Candidate artifacts do not contain one complete provenance signature.",
                )
            )
            continue
        if signatures != {expected.signature}:
            failures.append(
                ReuseReason(
                    "provenance_mismatch",
                    "Candidate provenance does not match the expected process signature.",
                    {
                        "expected_signature": expected.signature,
                        "candidate_signature": next(iter(signatures)),
                    },
                )
            )
            continue
        try:
            content_hash = module_content_hash(result.artifacts)
        except ContractError as exc:
            failures.append(ReuseReason("content_identity_missing", str(exc)))
            continue
        return ReuseCheck(
            ReuseSelection(
                reference=reference,
                result=result,
                artifact_bytes={
                    artifact.uri: snapshot.artifact_bytes[artifact.uri]
                    for artifact in result.artifacts
                },
                module_content_hash=content_hash,
            ),
            ReuseReason(
                "verified_reuse",
                f"Verified reusable result from run {reference.run_id!r}.",
                {
                    "run_id": reference.run_id,
                    "provenance_signature": expected.signature,
                },
            ),
        )
    return ReuseCheck(
        None,
        failures[0]
        if failures
        else ReuseReason("candidate_absent", "No explicit reuse candidate was supplied."),
    )

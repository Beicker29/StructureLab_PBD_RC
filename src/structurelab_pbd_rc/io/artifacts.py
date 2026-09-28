"""Isolated transactional publication for V2 run artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from structurelab_pbd_rc.contracts import (
    ArtifactManifest,
    ExecutionStatus,
    StageResult,
    validate_artifact_dependencies,
)
from structurelab_pbd_rc.core.exceptions import (
    PublicationCollisionError,
    PublicationError,
    PublicationValidationError,
)
from structurelab_pbd_rc.workflow.context import RunContext

if TYPE_CHECKING:
    from structurelab_pbd_rc.workflow.reuse import PublishedRunReference


_TRANSACTION_MARKER = ".transaction.json"
_RUN_MANIFEST = "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_artifact_path(uri: str) -> PurePosixPath:
    if not isinstance(uri, str) or not uri or "\\" in uri or "://" in uri:
        raise PublicationValidationError("Artifact URI must be a relative POSIX path.")
    path = PurePosixPath(uri)
    if path.is_absolute() or ".." in path.parts or uri.startswith("/"):
        raise PublicationValidationError("Artifact URI must remain inside its run directory.")
    if path.name in {_RUN_MANIFEST, _TRANSACTION_MARKER}:
        raise PublicationValidationError(f"Artifact URI {uri!r} is reserved for publication.")
    return path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class RecoveryRecord:
    transaction: str
    status: str
    final_path: str | None = None
    message: str = ""


class PublicationTransaction:
    """One private staging directory owned by exactly one V2 run identity."""

    def __init__(
        self,
        publisher: "TransactionalPublisher",
        context: RunContext,
        staging_path: Path,
        final_path: Path,
    ) -> None:
        self.publisher = publisher
        self.context = context
        self.staging_path = staging_path
        self.final_path = final_path
        self._ready = False

    def write_bytes(self, uri: str, data: bytes) -> Path:
        relative = _relative_artifact_path(uri)
        target = self.staging_path.joinpath(*relative.parts)
        if not _is_within(target, self.staging_path):
            raise PublicationValidationError("Artifact path escaped the staging directory.")
        if target.exists():
            raise PublicationValidationError(f"Artifact URI {uri!r} was already written.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def write_text(self, uri: str, text: str, *, encoding: str = "utf-8") -> Path:
        return self.write_bytes(uri, text.encode(encoding))

    def _write_run_manifest(self, stage_results: tuple[StageResult, ...]) -> None:
        manifests = tuple(
            artifact for result in stage_results for artifact in result.artifacts
        )
        self._validate_stage_results(stage_results, manifests)
        payload = {
            "schema_version": self.context.schema_version,
            "publication_status": "complete",
            "run_context": self.context.to_dict(),
            "stage_results": [result.to_dict() for result in stage_results],
            "artifacts": [manifest.to_dict() for manifest in manifests],
        }
        manifest_path = self.staging_path / _RUN_MANIFEST
        manifest_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def _validate_stage_results(
        self,
        stage_results: tuple[StageResult, ...],
        manifests: tuple[ArtifactManifest, ...],
    ) -> None:
        if not stage_results:
            raise PublicationValidationError("A publication requires at least one StageResult.")
        if any(result.execution_status is not ExecutionStatus.COMPLETED for result in stage_results):
            raise PublicationValidationError(
                "Only completed stage executions can be promoted as a complete run."
            )
        identities = [(result.module_id, result.stage_number) for result in stage_results]
        if len(identities) != len(set(identities)):
            raise PublicationValidationError("A run cannot contain duplicate stage results.")
        try:
            validate_artifact_dependencies(manifests)
        except ValueError as exc:
            raise PublicationValidationError(str(exc)) from exc

        declared: set[str] = set()
        for manifest in manifests:
            relative = _relative_artifact_path(manifest.uri)
            key = relative.as_posix().casefold()
            if key in declared:
                raise PublicationValidationError(
                    f"Multiple artifacts declare URI {relative.as_posix()!r}."
                )
            declared.add(key)
            path = self.staging_path.joinpath(*relative.parts)
            if not path.is_file():
                raise PublicationValidationError(
                    f"Declared artifact {manifest.artifact_id!r} was not staged."
                )
            if _sha256(path) != manifest.sha256:
                raise PublicationValidationError(
                    f"Declared artifact {manifest.artifact_id!r} has a SHA-256 mismatch."
                )

        actual = {
            path.relative_to(self.staging_path).as_posix().casefold()
            for path in self.staging_path.rglob("*")
            if path.is_file() and path.name != _TRANSACTION_MARKER
        }
        if actual != declared:
            extra = sorted(actual - declared)
            missing = sorted(declared - actual)
            details = []
            if extra:
                details.append(f"undeclared files: {', '.join(extra)}")
            if missing:
                details.append(f"missing files: {', '.join(missing)}")
            raise PublicationValidationError("Invalid staged artifact set; " + "; ".join(details))

    def mark_ready(self) -> None:
        self._ready = True
        self.publisher._write_marker(
            self.staging_path,
            context=self.context,
            final_path=self.final_path,
            state="ready",
        )

    def abort(self) -> None:
        if self.staging_path.exists():
            self.publisher._remove_staging_path(self.staging_path)


class TransactionalPublisher:
    """Publish under outputs/v2/project/revision/case/run without replacement."""

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root).resolve()
        self.v2_root = self.output_root / "v2"
        self.staging_root = self.v2_root / ".staging"

    def final_path(self, context: RunContext) -> Path:
        return self.v2_root.joinpath(
            context.project_id,
            context.design_revision,
            context.case_id,
            context.run_id,
        )

    def published_reference(
        self,
        context: RunContext,
        *,
        priority: int = 0,
    ) -> "PublishedRunReference":
        """Create an explicit, hash-addressed reference to an existing run."""

        from structurelab_pbd_rc.workflow.reuse import PublishedRunReference

        manifest_path = self.final_path(context) / _RUN_MANIFEST
        if not manifest_path.is_file():
            raise PublicationValidationError(
                f"Published run has no manifest: {manifest_path}."
            )
        return PublishedRunReference(
            project_id=context.project_id,
            design_revision=context.design_revision,
            case_id=context.case_id,
            run_id=context.run_id,
            manifest_sha256=_sha256(manifest_path),
            priority=priority,
        )

    def begin(self, context: RunContext) -> PublicationTransaction:
        if not isinstance(context, RunContext):
            raise TypeError("context must be a RunContext instance.")
        if context.publication_policy != "atomic":
            raise PublicationValidationError(
                f"Unsupported publication_policy {context.publication_policy!r}."
            )
        final_path = self.final_path(context)
        self._assert_final_available(final_path)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        staging_path = self.staging_root / f"{context.run_id}.{uuid4().hex}.tmp"
        staging_path.mkdir()
        self._write_marker(
            staging_path,
            context=context,
            final_path=final_path,
            state="staging",
        )
        return PublicationTransaction(self, context, staging_path, final_path)

    def publish(
        self,
        context: RunContext,
        stage_results: Iterable[StageResult],
        writer: Callable[[PublicationTransaction], None],
    ) -> Path:
        """Stage, validate, and atomically promote one immutable run."""

        transaction = self.begin(context)
        promotion_started = False
        try:
            self._before_write(transaction)
            writer(transaction)
            results = tuple(stage_results)
            transaction._write_run_manifest(results)
            self._before_promotion(transaction)
            transaction.mark_ready()
            promotion_started = True
            self._assert_final_available(transaction.final_path)
            transaction.final_path.parent.mkdir(parents=True, exist_ok=True)
            self._promote(transaction.staging_path, transaction.final_path)
            return transaction.final_path
        except Exception:
            if promotion_started:
                if transaction.final_path.exists() and not transaction.staging_path.exists():
                    self._validate_published_tree(transaction.final_path)
                    return transaction.final_path
            else:
                transaction.abort()
            raise

    def recover_temporaries(self) -> tuple[RecoveryRecord, ...]:
        """Discard incomplete staging and promote valid ready transactions."""

        if not self.staging_root.exists():
            return ()
        records: list[RecoveryRecord] = []
        for staging_path in sorted(self.staging_root.iterdir(), key=lambda item: item.name):
            if not staging_path.is_dir():
                records.append(
                    RecoveryRecord(staging_path.name, "error", message="not a directory")
                )
                continue
            try:
                if not _is_within(staging_path.resolve(), self.staging_root):
                    raise PublicationValidationError(
                        "Recovery candidate escaped the V2 staging root."
                    )
                marker = self._read_marker(staging_path)
                state = marker["state"]
                marker_context = RunContext.from_dict(marker["run_context"])
                final_path = self.v2_root.joinpath(*PurePosixPath(marker["final_relative"]).parts)
                if not _is_within(final_path, self.v2_root):
                    raise PublicationValidationError("Recovery target escaped the V2 root.")
                if final_path != self.final_path(marker_context):
                    raise PublicationValidationError(
                        "Recovery target does not match the marker run identity."
                    )
                if state == "staging":
                    self._remove_staging_path(staging_path)
                    records.append(RecoveryRecord(staging_path.name, "discarded"))
                    continue
                if state != "ready":
                    raise PublicationValidationError(f"Unknown transaction state {state!r}.")
                self._validate_published_tree(staging_path)
                try:
                    self._assert_final_available(final_path)
                except PublicationCollisionError as exc:
                    records.append(
                        RecoveryRecord(
                            staging_path.name,
                            "collision",
                            str(final_path),
                            str(exc),
                        )
                    )
                    continue
                final_path.parent.mkdir(parents=True, exist_ok=True)
                self._promote(staging_path, final_path)
                records.append(
                    RecoveryRecord(staging_path.name, "recovered", str(final_path))
                )
            except Exception as exc:
                records.append(
                    RecoveryRecord(staging_path.name, "error", message=str(exc))
                )
        return tuple(records)

    def _validate_published_tree(self, root: Path) -> None:
        manifest_path = root / _RUN_MANIFEST
        if not manifest_path.is_file():
            raise PublicationValidationError("A ready publication has no final manifest.")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            results = tuple(StageResult.from_dict(item) for item in payload["stage_results"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PublicationValidationError("The final run manifest is invalid.") from exc
        if payload.get("publication_status") != "complete":
            raise PublicationValidationError("The final run manifest is not complete.")
        if any(result.execution_status is not ExecutionStatus.COMPLETED for result in results):
            raise PublicationValidationError(
                "The final run manifest contains a non-completed stage result."
            )
        manifests = tuple(artifact for result in results for artifact in result.artifacts)
        try:
            validate_artifact_dependencies(manifests)
        except ValueError as exc:
            raise PublicationValidationError(str(exc)) from exc
        for manifest in manifests:
            path = root.joinpath(*_relative_artifact_path(manifest.uri).parts)
            if not path.is_file() or _sha256(path) != manifest.sha256:
                raise PublicationValidationError(
                    f"Published artifact {manifest.artifact_id!r} failed integrity validation."
                )

    def _assert_final_available(self, final_path: Path) -> None:
        if not _is_within(final_path, self.v2_root):
            raise PublicationValidationError("Final run path escaped the V2 output root.")
        if final_path.exists():
            raise PublicationCollisionError(
                f"Run output already exists and is immutable: {final_path}."
            )
        parent = final_path.parent
        if parent.exists():
            matching = [item for item in parent.iterdir() if item.name.casefold() == final_path.name.casefold()]
            if matching:
                raise PublicationCollisionError(
                    f"Run ID collides case-insensitively with {matching[0].name!r}."
                )

    def _write_marker(
        self,
        staging_path: Path,
        *,
        context: RunContext,
        final_path: Path,
        state: str,
    ) -> None:
        if not _is_within(staging_path, self.staging_root):
            raise PublicationValidationError("Transaction marker escaped the staging root.")
        relative = final_path.relative_to(self.v2_root).as_posix()
        payload = {
            "schema_version": context.schema_version,
            "state": state,
            "final_relative": relative,
            "run_context": context.to_dict(),
        }
        temporary = staging_path / f"{_TRANSACTION_MARKER}.tmp"
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, staging_path / _TRANSACTION_MARKER)

    def _read_marker(self, staging_path: Path) -> dict[str, Any]:
        marker_path = staging_path / _TRANSACTION_MARKER
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublicationValidationError("Invalid or missing transaction marker.") from exc
        if not isinstance(marker, dict):
            raise PublicationValidationError("Transaction marker must be a mapping.")
        return marker

    def _remove_staging_path(self, staging_path: Path) -> None:
        resolved = staging_path.resolve()
        if not _is_within(resolved, self.staging_root) or resolved == self.staging_root.resolve():
            raise PublicationValidationError("Refusing to remove a path outside V2 staging.")
        shutil.rmtree(resolved)

    def _before_write(self, transaction: PublicationTransaction) -> None:
        """Test seam before any artifact is written."""

    def _before_promotion(self, transaction: PublicationTransaction) -> None:
        """Test seam after validation and before the transaction becomes recoverable."""

    def _promote(self, staging_path: Path, final_path: Path) -> None:
        """Single same-volume directory rename; target replacement is forbidden."""

        os.replace(staging_path, final_path)


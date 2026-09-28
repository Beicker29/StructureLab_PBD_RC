"""V2-014 isolated transactional publication and recovery tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ArtifactManifest,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    StageResult,
)
from structurelab_pbd_rc.core.exceptions import (
    PublicationCollisionError,
    PublicationValidationError,
)
from structurelab_pbd_rc.io.artifacts import TransactionalPublisher
from structurelab_pbd_rc.workflow.context import RunContext


PAYLOAD = b'{"project":"tower_a"}'
URI = "00_project_objectives/data/project_spec.json"


def context(
    root: Path,
    *,
    project_id: str = "tower_a",
    revision: str = "rev_01",
    case_id: str = "case_01",
    run_id: str = "run_001",
) -> RunContext:
    return RunContext(
        schema_version="2",
        run_id=run_id,
        project_id=project_id,
        design_revision=revision,
        case_id=case_id,
        project_root=str(root.resolve()),
        code_version="0.1.0",
        environment={"python": "test"},
        resolved_configuration={"module": "project_objectives"},
    )


def result(payload: bytes = PAYLOAD) -> StageResult:
    artifact = ArtifactManifest(
        schema_version="2",
        artifact_id="project_spec",
        artifact_type="project_spec",
        module_id="project_objectives",
        stage_number="00",
        producer="tests.v2_publication",
        uri=URI,
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    return StageResult(
        schema_version="2",
        module_id="project_objectives",
        stage_number="00",
        execution_status=ExecutionStatus.COMPLETED,
        numerical_quality=NumericalQualityStatus.NOT_APPLICABLE,
        applicability=ApplicabilityStatus.APPLICABLE,
        performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
        artifacts=(artifact,),
    )


def publish(
    publisher: TransactionalPublisher,
    run_context: RunContext,
    payload: bytes = PAYLOAD,
) -> Path:
    return publisher.publish(
        run_context,
        (result(payload),),
        lambda transaction: transaction.write_bytes(URI, payload),
    )


def test_successful_publication_uses_isolated_identity_and_preserves_states(
    tmp_path: Path,
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    run_context = context(tmp_path)
    final = publish(publisher, run_context)

    assert final == (
        tmp_path / "outputs/v2/tower_a/rev_01/case_01/run_001"
    ).resolve()
    manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    stage = manifest["stage_results"][0]
    assert manifest["publication_status"] == "complete"
    assert stage["execution_status"] == "completed"
    assert stage["numerical_quality"] == "not_applicable"
    assert stage["applicability"] == "applicable"
    assert stage["performance_acceptance"] == "not_evaluated"


def test_failure_before_write_leaves_no_run_or_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    monkeypatch.setattr(
        publisher,
        "_before_write",
        lambda transaction: (_ for _ in ()).throw(RuntimeError("before-write")),
    )
    with pytest.raises(RuntimeError, match="before-write"):
        publish(publisher, context(tmp_path))
    assert not publisher.final_path(context(tmp_path)).exists()
    assert not list(publisher.staging_root.glob("*.tmp"))


def test_failure_during_write_removes_partial_staging(
    tmp_path: Path,
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")

    def failing_writer(transaction: object) -> None:
        transaction.write_bytes(URI, b"partial")  # type: ignore[attr-defined]
        raise RuntimeError("during-write")

    with pytest.raises(RuntimeError, match="during-write"):
        publisher.publish(context(tmp_path), (result(),), failing_writer)
    assert not publisher.final_path(context(tmp_path)).exists()
    assert not list(publisher.staging_root.glob("*.tmp"))


def test_failure_before_promotion_preserves_previous_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    previous_context = context(tmp_path, run_id="run_previous")
    previous = publish(publisher, previous_context)
    previous_hash = hashlib.sha256((previous / URI).read_bytes()).hexdigest()
    monkeypatch.setattr(
        publisher,
        "_before_promotion",
        lambda transaction: (_ for _ in ()).throw(RuntimeError("before-promotion")),
    )

    with pytest.raises(RuntimeError, match="before-promotion"):
        publish(publisher, context(tmp_path, run_id="run_new"))
    assert hashlib.sha256((previous / URI).read_bytes()).hexdigest() == previous_hash
    assert not publisher.final_path(context(tmp_path, run_id="run_new")).exists()
    assert not list(publisher.staging_root.glob("*.tmp"))


def test_failure_during_promotion_is_recoverable_and_preserves_previous_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    previous = publish(publisher, context(tmp_path, run_id="run_previous"))
    previous_bytes = (previous / URI).read_bytes()
    original_promote = publisher._promote
    monkeypatch.setattr(
        publisher,
        "_promote",
        lambda staging, final: (_ for _ in ()).throw(RuntimeError("during-promotion")),
    )

    new_context = context(tmp_path, run_id="run_recover")
    with pytest.raises(RuntimeError, match="during-promotion"):
        publish(publisher, new_context)
    ready = list(publisher.staging_root.glob("*.tmp"))
    assert len(ready) == 1
    assert not publisher.final_path(new_context).exists()
    assert (previous / URI).read_bytes() == previous_bytes

    monkeypatch.setattr(publisher, "_promote", original_promote)
    recovery = publisher.recover_temporaries()
    assert [item.status for item in recovery] == ["recovered"]
    assert (publisher.final_path(new_context) / URI).read_bytes() == PAYLOAD
    assert (previous / URI).read_bytes() == previous_bytes


def test_incomplete_temporary_is_discarded_by_recovery(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    transaction = publisher.begin(context(tmp_path, run_id="run_incomplete"))
    transaction.write_bytes(URI, b"partial")
    recovery = publisher.recover_temporaries()
    assert [item.status for item in recovery] == ["discarded"]
    assert not transaction.staging_path.exists()
    assert not transaction.final_path.exists()


def test_two_cases_and_two_revisions_coexist(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    contexts = (
        context(tmp_path, revision="rev_01", case_id="case_01"),
        context(tmp_path, revision="rev_01", case_id="case_02"),
        context(tmp_path, revision="rev_02", case_id="case_01"),
        context(tmp_path, revision="rev_02", case_id="case_02"),
    )
    paths = [publish(publisher, item) for item in contexts]
    assert len(set(paths)) == 4
    assert all((path / URI).read_bytes() == PAYLOAD for path in paths)


def test_run_id_collision_never_replaces_existing_output(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    run_context = context(tmp_path)
    final = publish(publisher, run_context)
    before = (final / URI).read_bytes()
    with pytest.raises(PublicationCollisionError, match="immutable"):
        publish(publisher, run_context, b"different")
    assert (final / URI).read_bytes() == before


def test_other_run_and_v1_outputs_cannot_be_deleted_or_replaced(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    v1_sentinel = output_root / "stage_01/keep.txt"
    v1_sentinel.parent.mkdir(parents=True)
    v1_sentinel.write_bytes(b"v1-historical")
    publisher = TransactionalPublisher(output_root)
    other = publish(publisher, context(tmp_path, run_id="other_run"))
    other_before = (other / URI).read_bytes()

    def escape_writer(transaction: object) -> None:
        transaction.write_bytes("../../other_run/erase.txt", b"bad")  # type: ignore[attr-defined]

    with pytest.raises(PublicationValidationError, match="inside its run"):
        publisher.publish(
            context(tmp_path, run_id="attacker"),
            (result(),),
            escape_writer,
        )
    assert (other / URI).read_bytes() == other_before
    assert v1_sentinel.read_bytes() == b"v1-historical"


def test_invalid_or_noncompleted_publication_is_not_promoted(tmp_path: Path) -> None:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    failed_result = replace(result(), execution_status=ExecutionStatus.FAILED)
    with pytest.raises(PublicationValidationError, match="Only completed"):
        publisher.publish(
            context(tmp_path, run_id="failed_run"),
            (failed_result,),
            lambda transaction: transaction.write_bytes(URI, PAYLOAD),
        )
    assert not publisher.final_path(context(tmp_path, run_id="failed_run")).exists()


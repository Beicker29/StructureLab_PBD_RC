"""V2-016 dependency invalidation and verified reuse tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from structurelab_pbd_rc.contracts import (
    ApplicabilityStatus,
    ArtifactDependency,
    ArtifactManifest,
    ExecutionStatus,
    NumericalQualityStatus,
    PerformanceAcceptanceStatus,
    StageResult,
)
from structurelab_pbd_rc.io.artifacts import TransactionalPublisher
from structurelab_pbd_rc.workflow.catalog import ModuleCatalog, ModuleDefinition
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.registry import (
    HandlerOutput,
    HandlerRegistry,
    StageExecutionRequest,
)
from structurelab_pbd_rc.workflow.reuse import (
    PublishedRunIndex,
    PublishedRunReference,
)
from structurelab_pbd_rc.workflow.runner import PlanStatus, WorkflowRunner


MODULES = ("project_objectives", "site_hazard", "baseline_model")
INPUT_A = "a" * 64
INPUT_B = "b" * 64


def catalog() -> ModuleCatalog:
    return ModuleCatalog(
        (
            ModuleDefinition("00", "project_objectives", "Root"),
            ModuleDefinition("01", "site_hazard", "Middle", ("project_objectives",)),
            ModuleDefinition("02", "baseline_model", "Leaf", ("site_hazard",)),
        )
    )


def context(
    tmp_path: Path,
    *,
    run_id: str,
    factor: float = 1.0,
    input_hash: str | None = INPUT_A,
    timestamp: str = "2026-09-26T10:00:00Z",
    absolute_path: str = r"C:\inputs\project.json",
    project_id: str = "tower_a",
    revision: str = "rev_01",
    case_id: str = "case_01",
) -> RunContext:
    return RunContext(
        schema_version="2",
        run_id=run_id,
        project_id=project_id,
        design_revision=revision,
        case_id=case_id,
        project_root=str(tmp_path.resolve()),
        code_version="0.1.0",
        environment={"python": "test"},
        resolved_configuration={
            "factor": factor,
            "timestamp": timestamp,
            "run_id": run_id,
            "input_path": absolute_path,
        },
        metadata={
            "input_hashes": {
                "project_objectives": (
                    {"project_input": input_hash} if input_hash is not None else {}
                ),
                "site_hazard": {},
                "baseline_model": {},
            }
        },
    )


def reusable_handler(
    calls: dict[str, int],
) -> Callable[[StageExecutionRequest], HandlerOutput]:
    def handler(request: StageExecutionRequest) -> HandlerOutput:
        calls[request.module.module_id] = calls.get(request.module.module_id, 0) + 1
        assert request.expected_provenance is not None
        payload = json.dumps(
            {"module_id": request.module.module_id, "value": 42},
            sort_keys=True,
        ).encode("utf-8")
        dependencies = tuple(
            ArtifactDependency(artifact.artifact_id, artifact.content_hash)
            for result in request.dependency_results.values()
            for artifact in result.artifacts
        )
        uri = (
            f"{request.module.stage_number}_{request.module.module_id}"
            "/data/result.json"
        )
        artifact = ArtifactManifest(
            schema_version="2",
            artifact_id=f"{request.module.module_id}_result",
            artifact_type="synthetic_result",
            module_id=request.module.module_id,
            stage_number=request.module.stage_number,
            producer="tests.v2_invalidation_reuse",
            uri=uri,
            sha256=hashlib.sha256(payload).hexdigest(),
            dependencies=dependencies,
            provenance=request.expected_provenance,
        )
        result = StageResult(
            schema_version="2",
            module_id=request.module.module_id,
            stage_number=request.module.stage_number,
            execution_status=ExecutionStatus.COMPLETED,
            numerical_quality=NumericalQualityStatus.CONVERGED,
            applicability=ApplicabilityStatus.APPLICABLE,
            performance_acceptance=PerformanceAcceptanceStatus.NOT_EVALUATED,
            artifacts=(artifact,),
        )
        return HandlerOutput(result, {uri: payload})

    return handler


def registry(
    calls: dict[str, int],
    *,
    root_version: str = "root-1.0",
) -> HandlerRegistry:
    versions = {
        "project_objectives": root_version,
        "site_hazard": "middle-1.0",
        "baseline_model": "leaf-1.0",
    }
    handlers = HandlerRegistry()
    for module_id in MODULES:
        handlers.register(
            module_id,
            reusable_handler(calls),
            implementation_version=versions[module_id],
            units={"force": "kN"},
            sign_conventions={"axial": "compression_positive"},
            required_input_ids=("project_input",) if module_id == "project_objectives" else (),
            reuse_allowed=True,
        )
    return handlers


def publish_baseline(
    tmp_path: Path,
) -> tuple[TransactionalPublisher, RunContext, PublishedRunReference]:
    publisher = TransactionalPublisher(tmp_path / "outputs")
    baseline = context(tmp_path, run_id="run_001")
    outcome = WorkflowRunner(
        catalog=catalog(),
        registry=registry({}),
        publisher=publisher,
    ).run(baseline, "baseline_model")
    assert outcome.completed
    reference = publisher.published_reference(baseline)
    return publisher, baseline, reference


def reuse_runner(
    publisher: TransactionalPublisher,
    reference: PublishedRunReference,
    calls: dict[str, int] | None = None,
    *,
    root_version: str = "root-1.0",
) -> WorkflowRunner:
    return WorkflowRunner(
        catalog=catalog(),
        registry=registry(calls if calls is not None else {}, root_version=root_version),
        publisher=publisher,
        reuse_index=PublishedRunIndex((reference,)),
    )


def artifact_path(
    publisher: TransactionalPublisher,
    run_context: RunContext,
    module_id: str,
) -> Path:
    number = {"project_objectives": "00", "site_hazard": "01", "baseline_model": "02"}[
        module_id
    ]
    return publisher.final_path(run_context) / f"{number}_{module_id}/data/result.json"


def replace_reference_hash(
    publisher: TransactionalPublisher,
    run_context: RunContext,
    reference: PublishedRunReference,
) -> PublishedRunReference:
    manifest = publisher.final_path(run_context) / "manifest.json"
    return PublishedRunReference(
        project_id=reference.project_id,
        design_revision=reference.design_revision,
        case_id=reference.case_id,
        run_id=reference.run_id,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        priority=reference.priority,
    )


def test_identical_inputs_are_reusable_and_handlers_are_not_called(tmp_path: Path) -> None:
    publisher, _, reference = publish_baseline(tmp_path)
    calls: dict[str, int] = {}
    current = context(tmp_path, run_id="run_002")
    runner = reuse_runner(publisher, reference, calls)
    plan = runner.plan("baseline_model", context=current)
    assert [plan.entry(item).status for item in MODULES] == [
        PlanStatus.REUSABLE,
        PlanStatus.REUSABLE,
        PlanStatus.REUSABLE,
    ]
    outcome = runner.run(current, "baseline_model")
    assert calls == {}
    assert outcome.completed
    assert all("reused_from" in item.metadata for item in outcome.stage_results)


def test_configuration_change_invalidates_transitively(tmp_path: Path) -> None:
    publisher, _, reference = publish_baseline(tmp_path)
    plan = reuse_runner(publisher, reference).plan(
        "baseline_model",
        context=context(tmp_path, run_id="run_002", factor=2.0),
    )
    assert plan.entry("project_objectives").status is PlanStatus.INVALIDATED
    assert plan.entry("project_objectives").reason_code == "provenance_mismatch"
    assert plan.entry("site_hazard").reason_code == "upstream_invalidated"
    assert plan.entry("baseline_model").reason_code == "upstream_invalidated"


def test_input_hash_change_invalidates_transitively(tmp_path: Path) -> None:
    publisher, _, reference = publish_baseline(tmp_path)
    plan = reuse_runner(publisher, reference).plan(
        "baseline_model",
        context=context(tmp_path, run_id="run_002", input_hash=INPUT_B),
    )
    assert all(plan.entry(item).status is PlanStatus.INVALIDATED for item in MODULES)


def test_implementation_version_change_invalidates_transitively(tmp_path: Path) -> None:
    publisher, _, reference = publish_baseline(tmp_path)
    plan = reuse_runner(
        publisher,
        reference,
        root_version="root-2.0",
    ).plan("baseline_model", context=context(tmp_path, run_id="run_002"))
    assert plan.entry("project_objectives").reason_code == "provenance_mismatch"
    assert plan.entry("site_hazard").reason_code == "upstream_invalidated"
    assert plan.entry("baseline_model").reason_code == "upstream_invalidated"


def test_only_timestamp_and_run_id_changes_do_not_invalidate(tmp_path: Path) -> None:
    publisher, _, reference = publish_baseline(tmp_path)
    current = context(
        tmp_path,
        run_id="run_999",
        timestamp="2030-01-01T00:00:00Z",
        absolute_path=r"D:\relocated\project.json",
    )
    plan = reuse_runner(publisher, reference).plan("baseline_model", context=current)
    assert all(plan.entry(item).status is PlanStatus.REUSABLE for item in MODULES)


def test_missing_required_input_hash_is_conservatively_invalidated(tmp_path: Path) -> None:
    publisher, _, reference = publish_baseline(tmp_path)
    plan = reuse_runner(publisher, reference).plan(
        "project_objectives",
        context=context(tmp_path, run_id="run_002", input_hash=None),
    )
    assert plan.entry("project_objectives").status is PlanStatus.INVALIDATED
    assert plan.entry("project_objectives").reason_code == "provenance_insufficient"


def test_incorrect_content_hash_is_not_reusable(tmp_path: Path) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    artifact_path(publisher, baseline, "project_objectives").write_bytes(b"corrupt")
    plan = reuse_runner(publisher, reference).plan(
        "project_objectives",
        context=context(tmp_path, run_id="run_002"),
    )
    assert plan.entry("project_objectives").status is PlanStatus.INVALIDATED
    assert plan.entry("project_objectives").reason_code == "content_hash_mismatch"


def test_incomplete_manifest_is_not_reusable(tmp_path: Path) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    manifest = publisher.final_path(baseline) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["publication_status"] = "incomplete"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    updated = replace_reference_hash(publisher, baseline, reference)
    plan = reuse_runner(publisher, updated).plan(
        "project_objectives",
        context=context(tmp_path, run_id="run_002"),
    )
    assert plan.entry("project_objectives").reason_code == "manifest_incomplete"


def test_incompatible_manifest_schema_is_not_reusable(tmp_path: Path) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    manifest = publisher.final_path(baseline) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["schema_version"] = "3"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    updated = replace_reference_hash(publisher, baseline, reference)
    plan = reuse_runner(publisher, updated).plan(
        "project_objectives",
        context=context(tmp_path, run_id="run_002"),
    )
    assert plan.entry("project_objectives").reason_code == "manifest_incomplete"


def test_qa_policy_rejects_nonconverged_candidate(tmp_path: Path) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    manifest = publisher.final_path(baseline) / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["stage_results"][0]["numerical_quality"] = "not_converged"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    updated = replace_reference_hash(publisher, baseline, reference)
    plan = reuse_runner(publisher, updated).plan(
        "project_objectives",
        context=context(tmp_path, run_id="run_002"),
    )
    assert plan.entry("project_objectives").reason_code == "qa_policy_rejected"


def test_absent_artifact_is_not_reusable(tmp_path: Path) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    artifact_path(publisher, baseline, "project_objectives").unlink()
    plan = reuse_runner(publisher, reference).plan(
        "project_objectives",
        context=context(tmp_path, run_id="run_002"),
    )
    assert plan.entry("project_objectives").reason_code == "artifact_missing"


def test_corrupt_dependency_invalidates_downstream(tmp_path: Path) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    artifact_path(publisher, baseline, "project_objectives").write_bytes(b"corrupt")
    plan = reuse_runner(publisher, reference).plan(
        "baseline_model",
        context=context(tmp_path, run_id="run_002"),
    )
    assert plan.entry("project_objectives").reason_code == "content_hash_mismatch"
    assert plan.entry("site_hazard").reason_code == "upstream_invalidated"
    assert plan.entry("baseline_model").reason_code == "upstream_invalidated"


@pytest.mark.parametrize(
    ("identity_change", "value"),
    (("project_id", "tower_b"), ("revision", "rev_02"), ("case_id", "case_02")),
)
def test_reuse_candidates_are_isolated_by_full_case_identity(
    tmp_path: Path,
    identity_change: str,
    value: str,
) -> None:
    publisher, _, reference = publish_baseline(tmp_path)
    kwargs = {identity_change: value}
    plan = reuse_runner(publisher, reference).plan(
        "project_objectives",
        context=context(tmp_path, run_id="run_002", **kwargs),
    )
    assert plan.entry("project_objectives").status is PlanStatus.READY
    assert plan.entry("project_objectives").reason_code == "candidate_absent"


def test_reuse_plan_is_read_only_and_uses_no_filesystem_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    root = publisher.final_path(baseline)
    before = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(Path, "glob", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("glob")))
    monkeypatch.setattr(Path, "rglob", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rglob")))
    current = context(tmp_path, run_id="run_002")
    plan = reuse_runner(publisher, reference).plan("baseline_model", context=current)
    assert plan.entry("baseline_model").status is PlanStatus.REUSABLE
    assert not publisher.final_path(current).exists()
    after = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in before
    }
    assert after == before


def test_resume_preserves_historical_run_physically(tmp_path: Path) -> None:
    publisher, baseline, reference = publish_baseline(tmp_path)
    old_root = publisher.final_path(baseline)
    old_manifest = (old_root / "manifest.json").read_bytes()
    old_artifacts = {
        module_id: artifact_path(publisher, baseline, module_id).read_bytes()
        for module_id in MODULES
    }
    current = context(tmp_path, run_id="run_002")
    outcome = reuse_runner(publisher, reference).run(current, "baseline_model")
    assert outcome.completed
    assert publisher.final_path(current).is_dir()
    assert (old_root / "manifest.json").read_bytes() == old_manifest
    assert {
        module_id: artifact_path(publisher, baseline, module_id).read_bytes()
        for module_id in MODULES
    } == old_artifacts


def test_v1_outputs_remain_intact_during_verified_reuse(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    sentinel = output_root / "stage_02" / "legacy.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"frozen-v1")
    publisher, _, reference = publish_baseline(tmp_path)
    before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    reuse_runner(publisher, reference).run(
        context(tmp_path, run_id="run_002"),
        "baseline_model",
    )
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == before

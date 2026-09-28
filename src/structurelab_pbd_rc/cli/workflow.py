"""Official V2 workflow command line, backed by contracts and WorkflowRunner."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import uuid4

import yaml

from structurelab_pbd_rc.compat.v1 import convert_v1_to_v2
from structurelab_pbd_rc.compat.v1.converter import REFERENCE_IDS, canonical_json_bytes
from structurelab_pbd_rc.contracts import ProjectSpec
from structurelab_pbd_rc.core.exceptions import (
    ConfigError, ContractError, PublicationError, WorkflowError,
)
from structurelab_pbd_rc.io.artifacts import TransactionalPublisher
from structurelab_pbd_rc.workflow.context import RunContext
from structurelab_pbd_rc.workflow.reuse import PublishedRunIndex, PublishedRunReference
from structurelab_pbd_rc.workflow.runner import PlanStatus, WorkflowRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="structurelab", description="StructureLab V2 workflow")
    command = parser.add_subparsers(dest="command", required=True)
    workflow = command.add_parser("workflow", help="Plan, run, or convert a V2 project")
    actions = workflow.add_subparsers(dest="action", required=True)
    for action in ("plan", "run"):
        item = actions.add_parser(action)
        item.add_argument("--project", required=True, type=Path, help="V2 ProjectSpec YAML")
        item.add_argument("--module", action="append", dest="modules", metavar="MODULE_ID")
        item.add_argument("--config", action="append", default=[], metavar="MODULE_ID=PATH")
        item.add_argument("--project-id")
        item.add_argument("--design-revision")
        item.add_argument("--case-id")
        item.add_argument("--run-id")
        item.add_argument("--output-root", type=Path, help="V2 output parent; defaults beside project.yaml")
        item.add_argument("--reuse-manifest", action="append", default=[], type=Path)
    convert = actions.add_parser("convert", help="Preview V1 to V2 conversion; --write publishes a new project")
    convert.add_argument("--project-template", required=True, type=Path)
    convert.add_argument("--stage-01", type=Path)
    convert.add_argument("--stage-02", type=Path)
    convert.add_argument("--stage-03", type=Path)
    convert.add_argument("--source-root", type=Path)
    convert.add_argument("--destination", type=Path)
    convert.add_argument("--write", action="store_true")
    return parser


def _resolve_from_project(path: Path, project_file: Path) -> Path:
    return (path if path.is_absolute() else project_file.parent / path).resolve()


def _project(path: Path) -> ProjectSpec:
    if not path.is_file():
        raise ConfigError(f"ProjectSpec file does not exist: {path}.")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigError("ProjectSpec YAML must contain a mapping.")
    return ProjectSpec.from_dict(value)


def _overrides(values: list[str], project_file: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        module_id, separator, raw_path = value.partition("=")
        if not separator or not module_id or not raw_path or module_id in result:
            raise ConfigError("--config requires unique MODULE_ID=PATH values.")
        result[module_id] = _resolve_from_project(Path(raw_path), project_file)
    return result


def _module_inputs(
    project: ProjectSpec, project_file: Path, selected: tuple[str, ...], overrides: dict[str, Path],
) -> tuple[dict[str, dict], dict[str, dict[str, str]]]:
    selected_ids = set(selected)
    if set(overrides) - (selected_ids & set(REFERENCE_IDS)):
        raise ConfigError("--config requires a selected module with a supported V2 configuration contract.")
    module_inputs: dict[str, dict] = {}
    input_hashes: dict[str, dict[str, str]] = {}
    source_records = project.metadata.get("v1_conversion", {}).get("source_records", {})
    for module_id, reference_id in REFERENCE_IDS.items():
        if module_id not in selected_ids:
            continue
        matches = [item for item in project.references if item.module_id == module_id and item.kind == "configuration"]
        if len(matches) != 1 or matches[0].reference_id != reference_id:
            raise ConfigError(f"ProjectSpec requires exactly one {reference_id} reference for {module_id}.")
        reference = matches[0]
        if reference.sha256 is None:
            raise ConfigError(f"Configuration reference {reference_id} requires sha256.")
        if module_id in overrides:
            path = overrides[module_id]
        else:
            uri = Path(reference.uri)
            if uri.is_absolute() or ".." in uri.parts:
                raise ConfigError(f"Configuration reference {reference_id} must remain inside the project directory.")
            path = _resolve_from_project(uri, project_file)
            if not path.is_relative_to(project_file.parent):
                raise ConfigError(f"Configuration reference {reference_id} escapes the project directory.")
        if not path.is_file():
            raise ConfigError(f"Configuration file does not exist: {path}.")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != reference.sha256:
            raise ConfigError(f"Configuration hash differs from ProjectSpec reference {reference_id}.")
        try:
            config = json.loads(content)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Configuration {reference_id} is not valid UTF-8 JSON.") from exc
        if not isinstance(config, dict) or canonical_json_bytes(config) != content:
            raise ConfigError(f"Configuration {reference_id} must use canonical V2 JSON bytes.")
        module_inputs[module_id] = config
        hashes = {reference_id: reference.sha256}
        records = source_records.get(module_id, []) if isinstance(source_records, dict) else []
        for index, record in enumerate(records, start=1):
            if isinstance(record, dict) and isinstance(record.get("sha256"), str):
                hashes[f"v1_source_{index}"] = record["sha256"]
        input_hashes[module_id] = hashes
    return module_inputs, input_hashes


def _reuse_index(paths: list[Path], project_file: Path, publisher: TransactionalPublisher) -> PublishedRunIndex:
    references: list[PublishedRunReference] = []
    for priority, raw in enumerate(paths):
        path = _resolve_from_project(raw, project_file)
        if not path.is_file():
            raise ConfigError(f"Reuse manifest does not exist: {path}.")
        content = path.read_bytes()
        try:
            payload = json.loads(content)
            old_context = RunContext.from_dict(payload["run_context"])
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise ConfigError(f"Reuse manifest has no valid V2 run context: {path}.") from exc
        if path != publisher.final_path(old_context) / "manifest.json":
            raise ConfigError("Reuse manifest must be under the selected V2 output root.")
        references.append(PublishedRunReference(
            project_id=old_context.project_id,
            design_revision=old_context.design_revision,
            case_id=old_context.case_id,
            run_id=old_context.run_id,
            manifest_sha256=hashlib.sha256(content).hexdigest(),
            priority=priority,
        ))
    return PublishedRunIndex(tuple(references))


def _workflow(args: argparse.Namespace) -> int:
    project_file = args.project.resolve()
    project = _project(project_file)
    for name in ("project_id", "design_revision", "case_id"):
        requested = getattr(args, name)
        if requested is not None and requested != getattr(project, name):
            raise ConfigError(f"--{name.replace('_', '-')} differs from ProjectSpec; edit project.yaml explicitly.")
    declared_modules = tuple(
        item.module_id for item in project.references
        if item.module_id is not None and item.kind == "configuration"
    )
    requested = tuple(args.modules) if args.modules else declared_modules
    if not requested:
        raise ConfigError("Select at least one --module or declare a module configuration reference.")
    output_root = _resolve_from_project(args.output_root or Path("outputs"), project_file)
    publisher = TransactionalPublisher(output_root)
    index = _reuse_index(args.reuse_manifest, project_file, publisher)
    runner = WorkflowRunner(publisher=publisher, reuse_index=index)
    order = runner.dag.execution_order(requested)
    module_inputs, module_hashes = _module_inputs(project, project_file, order, _overrides(args.config, project_file))
    project_hash = hashlib.sha256(project.to_json(indent=2).encode("utf-8")).hexdigest()
    context = RunContext.from_project_spec(
        project,
        run_id=args.run_id or ("preview" if args.action == "plan" else f"run_{uuid4().hex[:12]}"),
        project_root=project_file.parent,
        code_version=package_version("structurelab-pbd-rc"),
        environment={"python": sys.version.split()[0]},
        resolved_configuration={"project_spec": project.to_dict(), "module_inputs": module_inputs},
    )
    context = RunContext.from_dict({
        **context.to_dict(),
        "metadata": {"input_hashes": {"project_objectives": {"project_spec": project_hash}, **module_hashes}},
    })
    plan = runner.plan(requested, context=context)
    blocked = any(item.status in {PlanStatus.NOT_IMPLEMENTED, PlanStatus.BLOCKED} for item in plan.entries)
    if args.action == "plan" or blocked:
        print(json.dumps({
            "command": args.action, "project_id": project.project_id,
            "design_revision": project.design_revision, "case_id": project.case_id,
            "run_id": context.run_id, "plan": plan.to_dict(),
        }, indent=2, ensure_ascii=False))
        return 3 if blocked else 0
    outcome = runner.run(context, requested)
    print(json.dumps({
        "command": "run", "run_id": context.run_id,
        "plan": plan.to_dict(), "published_path": outcome.published_path,
        "stages": [
            {
                "module_id": item.module_id,
                "execution_status": item.execution_status.value,
                "numerical_quality": item.numerical_quality.value,
                "applicability": item.applicability.value,
                "performance_acceptance": item.performance_acceptance.value,
                "artifacts": len(item.artifacts),
                "warnings": [warning.to_dict() for warning in item.warnings],
                "errors": [error.to_dict() for error in item.errors],
            }
            for item in outcome.stage_results
        ],
    }, indent=2, ensure_ascii=False))
    return 0 if outcome.completed and outcome.published_path else 1


def _convert(args: argparse.Namespace) -> int:
    bundle = convert_v1_to_v2(
        template_path=args.project_template,
        stage_01=args.stage_01,
        stage_02=args.stage_02,
        stage_03=args.stage_03,
        source_root=args.source_root,
    )
    if args.write and args.destination is None:
        raise ConfigError("--write requires --destination.")
    summary = bundle.preview(args.destination)
    if args.write:
        project_path = bundle.write(args.destination)
        summary["status"] = "written"
        summary["project"] = str(project_path)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _convert(args) if args.action == "convert" else _workflow(args)
    except (ConfigError, ContractError, WorkflowError, PublicationError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"structurelab: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, (ConfigError, ContractError, WorkflowError, FileNotFoundError, ValueError, yaml.YAMLError)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

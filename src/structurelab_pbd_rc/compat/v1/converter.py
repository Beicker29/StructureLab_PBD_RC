"""Non-destructive V1 inputs to the existing V2 workflow contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from structurelab_pbd_rc.contracts import (
    BaseUnits, HazardLevel, InputReference, PerformanceObjective, ProjectSpec, SiteInfo,
)
from structurelab_pbd_rc.core.exceptions import ConfigError, ContractError
from structurelab_pbd_rc.design.stages.stage_01_hazard import validate_stage_01_config
from structurelab_pbd_rc.design.stages.stage_02_input_config import load_enabled_stage_02_inputs
from structurelab_pbd_rc.design.stages.stage_03_section_characterization import (
    _safe_sheet_folder_name, validate_stage_03_config,
)
from structurelab_pbd_rc.io.read_config import load_yaml_config
from structurelab_pbd_rc.io.read_xlsx import list_xlsx_sheets, read_xlsx_rows


MODULES = (
    "site_hazard", "material_characterization", "section_component_characterization",
)
REFERENCE_IDS = {
    "site_hazard": "hazard_configuration",
    "material_characterization": "material_configuration",
    "section_component_characterization": "section_configuration",
}


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} must be a mapping.")
    return dict(value)


def _exact_keys(value: Mapping[str, Any], allowed: set[str], *, name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigError(f"Cannot translate unknown {name} fields: {', '.join(unknown)}.")


def _source_record(path: Path, *, role: str, v1_id: str | None = None) -> dict[str, str]:
    result = {"role": role, "path": str(path.resolve()), "sha256": _sha256(path)}
    if v1_id is not None:
        result["v1_id"] = v1_id
    return result


def _read_template(path: Path) -> dict[str, Any]:
    template = load_yaml_config(path)
    required = {
        "schema_version", "project_id", "design_revision", "case_id", "site",
        "base_units", "performance_objectives", "hazard_levels", "v1_bindings",
    }
    _exact_keys(template, required | {"material_set_id", "metadata"}, name="template")
    missing = sorted(required - set(template))
    if missing:
        raise ConfigError("Conversion template lacks explicit fields: " + ", ".join(missing) + ".")
    if str(template["schema_version"]) != "2":
        raise ConfigError("Conversion template schema_version must be '2'.")
    return template


def _hazard(path: Path, binding: Mapping[str, Any], template: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    _exact_keys(binding, {"case_id"}, name="site_hazard binding")
    config = load_yaml_config(path)
    _exact_keys(config, {"stage_id", "case_id", "title", "units", "hazard"}, name="Stage 01")
    validate_stage_01_config(config)
    if config["case_id"] != binding.get("case_id"):
        raise ConfigError("Stage 01 case_id differs from the explicit site_hazard binding.")
    levels = _mapping(config["hazard"]["seismic"]["hazard_levels"], name="V1 hazard levels")
    declared = {item["hazard_level_id"]: item for item in template["hazard_levels"]}
    if set(levels) != set(declared):
        raise ConfigError("Template hazard_level_ids must match Stage 01 hazard levels exactly.")
    for level_id, level in levels.items():
        if float(level["return_period_years"]) != float(declared[level_id].get("return_period_years", -1)):
            raise ConfigError(f"Ambiguous return period for hazard level {level_id!r}.")
    converted = {**config, "schema_version": "2", "module_id": "site_hazard"}
    return converted, [_source_record(path, role="stage_01_configuration", v1_id=str(config["case_id"]))]


def _materials(path: Path, binding: Mapping[str, Any], template: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    _exact_keys(binding, {"project_id", "case_id"}, name="material_characterization binding")
    if not path.is_dir():
        raise ConfigError(f"Stage 02 source must be a directory: {path}.")
    items = load_enabled_stage_02_inputs(path)
    source_files = sorted(path.rglob("*.json"))
    if len(source_files) != len(items):
        raise ConfigError("Stage 02 includes disabled or untranslated JSON inputs; explicit selection is required.")
    if not isinstance(template.get("material_set_id"), str):
        raise ConfigError("material_set_id must be explicitly supplied for Stage 02 conversion.")
    project_id = str(template["project_id"])
    case_id = str(template["case_id"])
    if binding.get("project_id") != project_id or binding.get("case_id") != case_id:
        raise ConfigError("Stage 02 binding must match V2 project_id and case_id.")
    models: list[dict[str, Any]] = []
    records: list[dict[str, str]] = []
    for item in items:
        _exact_keys(item.raw_config, {"stage_id", "enabled", "title", "units", "inputs"}, name="Stage 02")
        if (item.project_id, item.case_id) != (project_id, case_id):
            raise ConfigError("Stage 02 project/case IDs differ from the explicit project binding.")
        models.append({
            "title": item.title,
            "parameter_set_id": f"{item.model_id}_parameters",
            "material_instance_id": f"{item.model_id}_instance",
            "resolved_inputs": item.resolved_inputs,
        })
        records.append(_source_record(item.source_path, role="stage_02_model", v1_id=item.model_id))
    return {
        "schema_version": "2",
        "material_set_id": template["material_set_id"],
        "models": models,
    }, records


def _sections(
    path: Path, binding: Mapping[str, Any], source_root: Path | None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    _exact_keys(binding, {"workbook_sha256", "confirmed_for_project_case"}, name="section binding")
    if binding.get("confirmed_for_project_case") is not True:
        raise ConfigError("Section source association with the V2 project/case must be explicitly confirmed.")
    config = load_yaml_config(path)
    _exact_keys(
        config,
        {"stage_id", "title", "units", "source", "curve_detection", "bilinearization", "cyclic_diagram"},
        name="Stage 03",
    )
    validate_stage_03_config(config)
    if config["stage_id"] != "stage_03":
        raise ConfigError("Stage 03 stage_id must remain 'stage_03'.")
    workbook = Path(config["source"]["workbook"])
    if not workbook.is_absolute():
        if source_root is None:
            raise ConfigError("A relative Stage 03 workbook requires explicit --source-root.")
        workbook = source_root / workbook
    workbook = workbook.resolve()
    if not workbook.is_file():
        raise ConfigError(f"Stage 03 workbook does not exist: {workbook}.")
    workbook_hash = _sha256(workbook)
    if binding.get("workbook_sha256") != workbook_hash:
        raise ConfigError("Stage 03 workbook hash differs from the explicit binding.")
    available = list_xlsx_sheets(workbook)
    requested = config["source"]["sheets"]
    selected = available if requested == "all" else ([requested] if isinstance(requested, str) else requested)
    if not isinstance(selected, list) or not selected or not all(isinstance(name, str) for name in selected):
        raise ConfigError("Stage 03 source.sheets must select one or more named worksheets.")
    if any(name not in available for name in selected):
        raise ConfigError("Stage 03 selected worksheet is absent from the workbook.")
    routes = [_safe_sheet_folder_name(name).casefold() for name in selected]
    if len(routes) != len(set(routes)):
        raise ConfigError("Stage 03 worksheet names collide after V1 folder sanitization.")
    worksheets = [{"sheet_name": name, "rows": read_xlsx_rows(workbook, sheet_name=name)} for name in selected]
    records = [
        _source_record(path, role="stage_03_configuration", v1_id="stage_03"),
        _source_record(workbook, role="stage_03_workbook"),
    ]
    return {
        "schema_version": "2",
        "service_config": config,
        "worksheets": worksheets,
        "source_metadata": {
            "source_type": "external_xlsx_moment_curvature",
            "configuration_sha256": records[0]["sha256"],
            "workbook_sha256": workbook_hash,
            "configuration_path": records[0]["path"],
            "workbook_path": records[1]["path"],
            "project_case_association": "explicitly_confirmed",
        },
    }, records


@dataclass(frozen=True)
class ConversionBundle:
    project: ProjectSpec
    module_bytes: dict[str, bytes]
    source_records: dict[str, list[dict[str, str]]]
    source_paths: tuple[Path, ...]

    def preview(self, destination: Path | None = None) -> dict[str, Any]:
        files = {
            f"modules/{module_id}.json": {
                "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
            }
            for module_id, content in self.module_bytes.items()
        }
        project_content = yaml.safe_dump(self.project.to_dict(), sort_keys=False, allow_unicode=True).encode("utf-8")
        files["project.yaml"] = {
            "sha256": hashlib.sha256(project_content).hexdigest(), "bytes": len(project_content),
        }
        return {
            "status": "preview", "destination": str(destination.resolve()) if destination else None,
            "project_id": self.project.project_id,
            "design_revision": self.project.design_revision,
            "case_id": self.project.case_id,
            "module_ids": list(self.module_bytes),
            "sources": self.source_records,
            "files": files,
        }

    def write(self, destination: Path) -> Path:
        target = destination.resolve()
        for source in self.source_paths:
            protected = source if source.is_dir() else source.parent
            if target == protected or target.is_relative_to(protected):
                raise ConfigError(f"Conversion destination must not be inside a V1 input directory: {target}.")
        if target.exists():
            raise ConfigError(f"Conversion destination already exists; refusing to overwrite: {target}.")
        target.mkdir(parents=True, exist_ok=False)
        modules_dir = target / "modules"
        modules_dir.mkdir()
        for module_id, content in self.module_bytes.items():
            with (modules_dir / f"{module_id}.json").open("xb") as stream:
                stream.write(content)
        with (target / "project.yaml").open("xb") as stream:
            stream.write(yaml.safe_dump(self.project.to_dict(), sort_keys=False, allow_unicode=True).encode("utf-8"))
        return target / "project.yaml"


def convert_v1_to_v2(
    *, template_path: str | Path,
    stage_01: str | Path | None = None,
    stage_02: str | Path | None = None,
    stage_03: str | Path | None = None,
    source_root: str | Path | None = None,
) -> ConversionBundle:
    """Build a preview in memory. Only ConversionBundle.write creates files."""
    paths = {
        "site_hazard": Path(stage_01).resolve() if stage_01 is not None else None,
        "material_characterization": Path(stage_02).resolve() if stage_02 is not None else None,
        "section_component_characterization": Path(stage_03).resolve() if stage_03 is not None else None,
    }
    selected = {key: path for key, path in paths.items() if path is not None}
    if not selected:
        raise ConfigError("At least one V1 stage source must be specified.")
    template_file = Path(template_path).resolve()
    template = _read_template(template_file)
    bindings = _mapping(template["v1_bindings"], name="v1_bindings")
    if set(bindings) != set(selected):
        raise ConfigError("v1_bindings must name exactly the selected V1 source modules.")
    module_inputs: dict[str, dict[str, Any]] = {}
    source_records: dict[str, list[dict[str, str]]] = {}
    if paths["site_hazard"] is not None:
        module_inputs["site_hazard"], source_records["site_hazard"] = _hazard(
            paths["site_hazard"], _mapping(bindings["site_hazard"], name="site_hazard binding"), template,
        )
    if paths["material_characterization"] is not None:
        module_inputs["material_characterization"], source_records["material_characterization"] = _materials(
            paths["material_characterization"],
            _mapping(bindings["material_characterization"], name="material binding"), template,
        )
    if paths["section_component_characterization"] is not None:
        module_inputs["section_component_characterization"], source_records["section_component_characterization"] = _sections(
            paths["section_component_characterization"],
            _mapping(bindings["section_component_characterization"], name="section binding"),
            Path(source_root).resolve() if source_root is not None else None,
        )
    module_bytes = {module_id: canonical_json_bytes(config) for module_id, config in module_inputs.items()}
    references = tuple(
        InputReference(
            reference_id=REFERENCE_IDS[module_id], kind="configuration",
            uri=f"modules/{module_id}.json", module_id=module_id,
            sha256=hashlib.sha256(content).hexdigest(), schema_version="2",
        )
        for module_id, content in module_bytes.items()
    )
    metadata = _mapping(template.get("metadata", {}), name="template metadata")
    if "v1_conversion" in metadata:
        raise ConfigError("template metadata.v1_conversion is reserved for source provenance.")
    metadata["v1_conversion"] = {"source_records": source_records, "method": "explicit_v1_to_v2"}
    try:
        project = ProjectSpec(
            schema_version=str(template["schema_version"]),
            project_id=template["project_id"],
            design_revision=template["design_revision"],
            case_id=template["case_id"],
            site=SiteInfo.from_dict(_mapping(template["site"], name="site")),
            base_units=BaseUnits.from_dict(_mapping(template["base_units"], name="base_units")),
            performance_objectives=tuple(
                PerformanceObjective.from_dict(_mapping(item, name="performance objective"))
                for item in template["performance_objectives"]
            ),
            hazard_levels=tuple(
                HazardLevel.from_dict(_mapping(item, name="hazard level"))
                for item in template["hazard_levels"]
            ),
            references=references,
            metadata=metadata,
        )
    except (KeyError, TypeError, ContractError) as exc:
        raise ConfigError(f"Conversion template does not satisfy ProjectSpec: {exc}") from exc
    sources = tuple(path for path in paths.values() if path is not None)
    if paths["section_component_characterization"] is not None:
        sources += (Path(source_records["section_component_characterization"][1]["path"]),)
    return ConversionBundle(project, module_bytes, source_records, sources)

"""Discovery and validation for independent Stage 2 model JSON inputs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.io.read_config import load_json_config


MATERIALS = (
    "ductile_reinforcing_steel",
    "nonductile_reinforcing_steel",
    "confined_concrete",
    "unconfined_concrete",
)
ANALYSIS_TYPES = ("monotonic", "cyclic")
EXPECTED_UNITS = {"length": "mm", "stress": "MPa", "strain": "mm/mm"}
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class Stage02ModelInput:
    """One enabled model JSON resolved from its material/behavior path."""

    source_path: Path
    title: str
    project_id: str
    case_id: str
    model_id: str
    material: str
    analysis_type: str
    units: dict[str, str]
    raw_config: dict[str, Any]
    resolved_inputs: dict[str, Any]

    @property
    def combination_key(self) -> tuple[str, str, str, str]:
        """Return the case-local material/model identity."""

        return (
            self.project_id.casefold(),
            self.case_id.casefold(),
            self.material.casefold(),
            self.model_id.casefold(),
        )

    @property
    def model_definition_key(self) -> tuple[str, str, str]:
        """Return the unique material/behavior/model definition identity."""

        return (
            self.material.casefold(),
            self.analysis_type.casefold(),
            self.model_id.casefold(),
        )

    @property
    def output_route_key(self) -> tuple[str, str, str, str, str]:
        """Return the case-insensitive output route identity."""

        return (
            self.project_id.casefold(),
            self.case_id.casefold(),
            self.analysis_type.casefold(),
            self.material.casefold(),
            self.model_id.casefold(),
        )


def _validate_identifier(value: Any, *, name: str) -> str:
    identifier = str(value).strip()
    if not identifier or not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ConfigError(
            f"{name} must match {IDENTIFIER_PATTERN.pattern!r}. Received {value!r}."
        )
    return identifier


def _validate_directory_layout(root: Path) -> list[Path]:
    direct_entries = list(root.iterdir())
    unexpected_root_entries = sorted(
        entry.name
        for entry in direct_entries
        if not entry.is_dir() or entry.name not in MATERIALS
    )
    missing_materials = sorted(set(MATERIALS) - {entry.name for entry in direct_entries})
    if unexpected_root_entries or missing_materials:
        details: list[str] = []
        if unexpected_root_entries:
            details.append(f"unexpected: {', '.join(unexpected_root_entries)}")
        if missing_materials:
            details.append(f"missing: {', '.join(missing_materials)}")
        raise ConfigError(
            "configs/stage_02 must contain only the four material directories ("
            + "; ".join(details)
            + ")."
        )

    json_paths: list[Path] = []
    for material in MATERIALS:
        material_root = root / material
        behavior_entries = list(material_root.iterdir())
        unexpected_behaviors = sorted(
            entry.name
            for entry in behavior_entries
            if not entry.is_dir() or entry.name not in ANALYSIS_TYPES
        )
        missing_behaviors = sorted(
            set(ANALYSIS_TYPES) - {entry.name for entry in behavior_entries}
        )
        if unexpected_behaviors or missing_behaviors:
            raise ConfigError(
                f"{material_root} must contain only monotonic and cyclic directories."
            )
        for analysis_type in ANALYSIS_TYPES:
            behavior_root = material_root / analysis_type
            for entry in behavior_root.iterdir():
                if entry.is_file() and entry.suffix.lower() == ".json":
                    json_paths.append(entry)
                elif entry.name != ".gitkeep":
                    raise ConfigError(
                        f"Only independent JSON model inputs are allowed in {behavior_root}: "
                        f"{entry.name}"
                    )
    return sorted(json_paths, key=lambda path: str(path).casefold())


def _path_identity(path: Path) -> tuple[str, str]:
    analysis_type = path.parent.name
    material = path.parent.parent.name
    if material not in MATERIALS or analysis_type not in ANALYSIS_TYPES:
        raise ConfigError(
            f"Stage 2 model JSON must be directly under <material>/<monotonic|cyclic>: {path}"
        )
    return material, analysis_type


def _load_model_input(path: Path) -> tuple[Stage02ModelInput, bool]:
    config = load_json_config(path)
    require_keys(
        config,
        ("stage_id", "enabled", "title", "units", "inputs"),
        context=f"Stage 2 model input {path}",
    )
    if config["stage_id"] != "stage_02":
        raise ConfigError(f"{path}.stage_id must be stage_02.")
    if not isinstance(config["enabled"], bool):
        raise ConfigError(f"{path}.enabled must be true or false.")
    units = config["units"]
    inputs = config["inputs"]
    if not isinstance(units, Mapping) or dict(units) != EXPECTED_UNITS:
        raise ConfigError(f"{path}.units must be exactly {EXPECTED_UNITS!r}.")
    if not isinstance(inputs, Mapping):
        raise ConfigError(f"{path}.inputs must be an object.")
    require_keys(
        inputs,
        ("project_id", "case_id", "model_id", "parameters"),
        context=f"{path}.inputs",
    )
    if not isinstance(inputs["parameters"], Mapping):
        raise ConfigError(f"{path}.inputs.parameters must be an object.")

    material, analysis_type = _path_identity(path)
    project_id = _validate_identifier(
        inputs["project_id"],
        name=f"{path}.inputs.project_id",
    )
    case_id = _validate_identifier(inputs["case_id"], name=f"{path}.inputs.case_id")
    model_id = _validate_identifier(inputs["model_id"], name=f"{path}.inputs.model_id")
    if path.stem != model_id:
        raise ConfigError(
            f"{path}.inputs.model_id must match the JSON filename stem "
            f"{path.stem!r}."
        )
    resolved = {
        key: deepcopy(value)
        for key, value in inputs.items()
        if key not in {"project_id", "case_id", "model_id"}
    }
    resolved.update(
        {
            "case_id": case_id,
            "material": material,
            "analysis_type": analysis_type,
            "model": model_id,
            "units": deepcopy(dict(units)),
        }
    )
    return (
        Stage02ModelInput(
            source_path=path.resolve(),
            title=str(config["title"]),
            project_id=project_id,
            case_id=case_id,
            model_id=model_id,
            material=material,
            analysis_type=analysis_type,
            units=deepcopy(dict(units)),
            raw_config=deepcopy(config),
            resolved_inputs=resolved,
        ),
        bool(config["enabled"]),
    )


def _validate_identifiers_and_routes(inputs: list[Stage02ModelInput]) -> None:
    project_spelling: dict[str, str] = {}
    case_spelling: dict[tuple[str, str], str] = {}
    model_definitions: dict[tuple[str, str, str], Path] = {}
    combinations: dict[tuple[str, str, str, str], Path] = {}
    routes: dict[tuple[str, str, str, str, str], Path] = {}
    for item in inputs:
        project_key = item.project_id.casefold()
        prior_project = project_spelling.setdefault(project_key, item.project_id)
        if prior_project != item.project_id:
            raise ConfigError(
                f"Duplicate project identifier differs only by case: "
                f"{prior_project!r} and {item.project_id!r}."
            )
        case_key = (project_key, item.case_id.casefold())
        prior_case = case_spelling.setdefault(case_key, item.case_id)
        if prior_case != item.case_id:
            raise ConfigError(
                f"Duplicate case identifier differs only by case in project "
                f"{item.project_id}: {prior_case!r} and {item.case_id!r}."
            )
        if item.model_definition_key in model_definitions:
            raise ConfigError(
                "Only one JSON file is allowed per constitutive model: "
                f"{item.source_path} conflicts with "
                f"{model_definitions[item.model_definition_key]}."
            )
        model_definitions[item.model_definition_key] = item.source_path
        if item.combination_key in combinations:
            raise ConfigError(
                "Repeated material/model combination for project/case: "
                f"{item.source_path} conflicts with {combinations[item.combination_key]}."
            )
        combinations[item.combination_key] = item.source_path
        if item.output_route_key in routes:
            raise ConfigError(
                f"Stage 2 output path collision: {item.source_path} conflicts with "
                f"{routes[item.output_route_key]}."
            )
        routes[item.output_route_key] = item.source_path


def load_enabled_stage_02_inputs(path: str | Path) -> list[Stage02ModelInput]:
    """Load and jointly validate every enabled Stage 2 model JSON."""

    requested_path = Path(path).resolve()
    if requested_path.is_dir():
        json_paths = _validate_directory_layout(requested_path)
    else:
        raise ConfigError(
            f"Stage 2 input must be the directory containing all model JSON files: {path}"
        )
    if not json_paths:
        raise ConfigError(f"No Stage 2 model JSON files found under {path}.")

    all_inputs: list[tuple[Stage02ModelInput, bool]] = []
    for json_path in json_paths:
        item, enabled = _load_model_input(json_path)
        all_inputs.append((item, enabled))
    _validate_identifiers_and_routes([item for item, _ in all_inputs])
    enabled_inputs = [item for item, enabled in all_inputs if enabled]
    if not enabled_inputs:
        raise ConfigError(f"No enabled Stage 2 model JSON files found under {path}.")
    return enabled_inputs

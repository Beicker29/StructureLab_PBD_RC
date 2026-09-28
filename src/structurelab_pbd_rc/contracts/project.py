"""Versioned project and Stage 00 contracts."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, ClassVar

from structurelab_pbd_rc.contracts._common import (
    V2_SCHEMA_VERSION,
    copy_json_mapping,
    dataclass_field_names,
    ensure_mapping,
    ensure_unique_ids,
    reject_unknown_fields,
    validate_identifier,
    validate_non_empty,
    validate_positive,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts._module_identity import MODULE_NUMBER_BY_ID
from structurelab_pbd_rc.core.exceptions import ContractError


@dataclass(frozen=True)
class SiteInfo:
    """Project site identity and location, without normative interpretation."""

    site_id: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    elevation: float | None = None
    coordinate_reference_system: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.site_id, name="site.site_id")
        validate_non_empty(self.name, name="site.name")
        if self.latitude is not None:
            latitude = float(self.latitude)
            if not math.isfinite(latitude) or not -90 <= latitude <= 90:
                raise ContractError("site.latitude must be between -90 and 90 degrees.")
            object.__setattr__(self, "latitude", latitude)
        if self.longitude is not None:
            longitude = float(self.longitude)
            if not math.isfinite(longitude) or not -180 <= longitude <= 180:
                raise ContractError("site.longitude must be between -180 and 180 degrees.")
            object.__setattr__(self, "longitude", longitude)
        if self.elevation is not None:
            elevation = float(self.elevation)
            if not math.isfinite(elevation):
                raise ContractError("site.elevation must be finite when provided.")
            object.__setattr__(self, "elevation", elevation)
        if self.coordinate_reference_system is not None:
            validate_non_empty(
                self.coordinate_reference_system,
                name="site.coordinate_reference_system",
            )
        object.__setattr__(self, "metadata", copy_json_mapping(self.metadata, name="site.metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation": self.elevation,
            "coordinate_reference_system": self.coordinate_reference_system,
            "metadata": copy_json_mapping(self.metadata, name="site.metadata"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SiteInfo":
        reject_unknown_fields(
            data,
            {
                "site_id", "name", "latitude", "longitude", "elevation",
                "coordinate_reference_system", "metadata",
            },
            name="SiteInfo",
        )
        return cls(**data)


@dataclass(frozen=True)
class BaseUnits:
    """Declared project base units; dimensional conversion belongs to V2-013."""

    length: str
    force: str
    time: str
    mass: str | None = None
    temperature: str | None = None

    def __post_init__(self) -> None:
        for name in ("length", "force", "time"):
            validate_non_empty(getattr(self, name), name=f"base_units.{name}")
        for name in ("mass", "temperature"):
            value = getattr(self, name)
            if value is not None:
                validate_non_empty(value, name=f"base_units.{name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "length": self.length,
            "force": self.force,
            "time": self.time,
            "mass": self.mass,
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseUnits":
        reject_unknown_fields(
            data, {"length", "force", "time", "mass", "temperature"}, name="BaseUnits"
        )
        return cls(**data)


@dataclass(frozen=True)
class HazardLevel:
    """A named hazard level; no code-specific rule is embedded here."""

    hazard_level_id: str
    name: str
    description: str = ""
    return_period_years: float | None = None
    exceedance_probability: float | None = None
    time_horizon_years: float | None = None
    source_reference_id: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.hazard_level_id, name="hazard_level_id")
        validate_non_empty(self.name, name=f"hazard_levels[{self.hazard_level_id}].name")
        if self.return_period_years is not None:
            validate_positive(self.return_period_years, name="return_period_years")
        if self.time_horizon_years is not None:
            validate_positive(self.time_horizon_years, name="time_horizon_years")
        if self.exceedance_probability is not None:
            probability = float(self.exceedance_probability)
            if not 0 < probability <= 1:
                raise ContractError("exceedance_probability must be in the interval (0, 1].")
        if self.source_reference_id is not None:
            validate_identifier(self.source_reference_id, name="source_reference_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hazard_level_id": self.hazard_level_id,
            "name": self.name,
            "description": self.description,
            "return_period_years": self.return_period_years,
            "exceedance_probability": self.exceedance_probability,
            "time_horizon_years": self.time_horizon_years,
            "source_reference_id": self.source_reference_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HazardLevel":
        reject_unknown_fields(data, dataclass_field_names(cls), name="HazardLevel")
        return cls(**data)


@dataclass(frozen=True)
class PerformanceObjective:
    """A project objective linked to one or more declared hazard levels."""

    objective_id: str
    name: str
    hazard_level_ids: tuple[str, ...]
    description: str = ""
    acceptance_criteria_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "hazard_level_ids", tuple(self.hazard_level_ids))
        object.__setattr__(
            self,
            "acceptance_criteria_references",
            tuple(self.acceptance_criteria_references),
        )
        validate_identifier(self.objective_id, name="objective_id")
        validate_non_empty(self.name, name=f"performance_objectives[{self.objective_id}].name")
        if not self.hazard_level_ids:
            raise ContractError(
                f"Performance objective {self.objective_id!r} must reference a hazard level."
            )
        for value in self.hazard_level_ids:
            validate_identifier(value, name="hazard_level_ids")
        for value in self.acceptance_criteria_references:
            validate_identifier(value, name="acceptance_criteria_references")
        ensure_unique_ids(self.hazard_level_ids, name="hazard_level_id reference")
        ensure_unique_ids(
            self.acceptance_criteria_references,
            name="acceptance criteria reference",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "name": self.name,
            "hazard_level_ids": list(self.hazard_level_ids),
            "description": self.description,
            "acceptance_criteria_references": list(self.acceptance_criteria_references),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerformanceObjective":
        reject_unknown_fields(data, dataclass_field_names(cls), name="PerformanceObjective")
        values = dict(data)
        values["hazard_level_ids"] = tuple(values.get("hazard_level_ids", ()))
        values["acceptance_criteria_references"] = tuple(
            values.get("acceptance_criteria_references", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class InputReference:
    """Reference to a project configuration or input without reading it."""

    reference_id: str
    kind: str
    uri: str
    module_id: str | None = None
    sha256: str | None = None
    schema_version: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.reference_id, name="reference_id")
        if self.kind not in {"configuration", "input", "criteria", "source"}:
            raise ContractError(
                "reference kind must be one of 'configuration', 'input', 'criteria', or 'source'."
            )
        validate_non_empty(self.uri, name=f"references[{self.reference_id}].uri")
        if self.module_id is not None:
            validate_identifier(self.module_id, name="module_id", semantic=True)
            if self.module_id not in MODULE_NUMBER_BY_ID:
                raise ContractError(f"Unknown V2 module_id {self.module_id!r}.")
        if self.sha256 is not None:
            _validate_sha256(self.sha256, name="sha256")
        if self.schema_version is not None:
            validate_non_empty(self.schema_version, name="reference.schema_version")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "kind": self.kind,
            "uri": self.uri,
            "module_id": self.module_id,
            "sha256": self.sha256,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InputReference":
        reject_unknown_fields(data, dataclass_field_names(cls), name="InputReference")
        return cls(**data)


def _validate_sha256(value: str, *, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdefABCDEF" for character in value):
        raise ContractError(f"{name} must be a 64-character hexadecimal SHA-256 digest.")


@dataclass(frozen=True)
class ProjectSpec:
    """Minimal versioned contract for Stage 00 project objectives."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    project_id: str
    design_revision: str
    case_id: str
    site: SiteInfo
    base_units: BaseUnits
    performance_objectives: tuple[PerformanceObjective, ...]
    hazard_levels: tuple[HazardLevel, ...]
    references: tuple[InputReference, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "performance_objectives", tuple(self.performance_objectives))
        object.__setattr__(self, "hazard_levels", tuple(self.hazard_levels))
        object.__setattr__(self, "references", tuple(self.references))
        validate_schema_version(self.schema_version)
        for name in ("project_id", "design_revision", "case_id"):
            validate_identifier(getattr(self, name), name=name)
        if not self.performance_objectives:
            raise ContractError("ProjectSpec must declare at least one performance objective.")
        if not self.hazard_levels:
            raise ContractError("ProjectSpec must declare at least one hazard level.")
        if not any(item.kind in {"configuration", "input"} for item in self.references):
            raise ContractError(
                "ProjectSpec must declare at least one configuration or input reference."
            )
        ensure_unique_ids(
            (item.objective_id for item in self.performance_objectives),
            name="objective_id",
        )
        ensure_unique_ids(
            (item.hazard_level_id for item in self.hazard_levels),
            name="hazard_level_id",
        )
        ensure_unique_ids(
            (item.reference_id for item in self.references),
            name="reference_id",
        )
        hazard_ids = {item.hazard_level_id.casefold() for item in self.hazard_levels}
        reference_ids = {item.reference_id.casefold() for item in self.references}
        for hazard_level in self.hazard_levels:
            source_id = hazard_level.source_reference_id
            if source_id is not None and source_id.casefold() not in reference_ids:
                raise ContractError(
                    f"Hazard level {hazard_level.hazard_level_id!r} references unknown source "
                    f"{source_id!r}."
                )
        for objective in self.performance_objectives:
            missing_hazards = [
                item for item in objective.hazard_level_ids if item.casefold() not in hazard_ids
            ]
            missing_criteria = [
                item
                for item in objective.acceptance_criteria_references
                if item.casefold() not in reference_ids
            ]
            if missing_hazards:
                raise ContractError(
                    f"Objective {objective.objective_id!r} references unknown hazard levels: "
                    f"{', '.join(missing_hazards)}."
                )
            if missing_criteria:
                raise ContractError(
                    f"Objective {objective.objective_id!r} references unknown criteria: "
                    f"{', '.join(missing_criteria)}."
                )
        object.__setattr__(
            self, "metadata", copy_json_mapping(self.metadata, name="ProjectSpec.metadata")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "design_revision": self.design_revision,
            "case_id": self.case_id,
            "site": self.site.to_dict(),
            "base_units": self.base_units.to_dict(),
            "performance_objectives": [item.to_dict() for item in self.performance_objectives],
            "hazard_levels": [item.to_dict() for item in self.hazard_levels],
            "references": [item.to_dict() for item in self.references],
            "metadata": copy_json_mapping(self.metadata, name="ProjectSpec.metadata"),
        }

    @property
    def units(self) -> BaseUnits:
        """Alias for consumers that call the base-unit declaration ``units``."""

        return self.base_units

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectSpec":
        mapping = ensure_mapping(data, name="ProjectSpec")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="ProjectSpec")
        values = dict(mapping)
        validate_schema_version(values.get("schema_version"))
        values["site"] = SiteInfo.from_dict(dict(ensure_mapping(values.get("site"), name="site")))
        values["base_units"] = BaseUnits.from_dict(
            dict(ensure_mapping(values.get("base_units"), name="base_units"))
        )
        values["performance_objectives"] = tuple(
            PerformanceObjective.from_dict(dict(ensure_mapping(item, name="performance_objective")))
            for item in values.get("performance_objectives", ())
        )
        values["hazard_levels"] = tuple(
            HazardLevel.from_dict(dict(ensure_mapping(item, name="hazard_level")))
            for item in values.get("hazard_levels", ())
        )
        values["references"] = tuple(
            InputReference.from_dict(dict(ensure_mapping(item, name="reference")))
            for item in values.get("references", ())
        )
        return cls(**values)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "ProjectSpec":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("ProjectSpec JSON is invalid.") from exc
        return cls.from_dict(dict(ensure_mapping(data, name="ProjectSpec")))


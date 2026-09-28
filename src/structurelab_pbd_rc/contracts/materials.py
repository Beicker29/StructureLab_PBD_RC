"""Solver-neutral physical material identity and Stage 03 result references."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from structurelab_pbd_rc.contracts._common import (
    V2_SCHEMA_VERSION,
    dataclass_field_names,
    ensure_mapping,
    ensure_unique_ids,
    parse_enum,
    reject_unknown_fields,
    validate_identifier,
    validate_non_empty,
    validate_positive,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts.artifacts import ArtifactDependency, ArtifactManifest
from structurelab_pbd_rc.contracts.boundaries import (
    BoundaryDefinition,
    PhysicalQuantity,
    ReferenceSystem,
    SignConvention,
)
from structurelab_pbd_rc.core.exceptions import ContractError, UnitBoundaryError


class MaterialType(str, Enum):
    CONCRETE = "concrete"
    REINFORCING_STEEL = "reinforcing_steel"


_INTERNAL_UNITS = {"length": "mm", "stress": "MPa", "force": "kN"}
_STRENGTHS_BY_TYPE = {
    MaterialType.CONCRETE: frozenset({"fc"}),
    MaterialType.REINFORCING_STEEL: frozenset({"fy", "fu"}),
}


@dataclass(frozen=True)
class ConstitutiveReference:
    """A role-specific pointer to a published Stage 03 scientific result."""

    role: str
    model_id: str
    project_id: str
    design_revision: str
    case_id: str
    run_id: str
    artifact: ArtifactManifest

    def __post_init__(self) -> None:
        validate_identifier(self.role, name="constitutive role", semantic=True)
        for name in ("model_id", "project_id", "design_revision", "case_id", "run_id"):
            validate_identifier(getattr(self, name), name=f"constitutive_reference.{name}")
        if not isinstance(self.artifact, ArtifactManifest):
            raise ContractError("constitutive_reference.artifact must be an ArtifactManifest.")
        if (
            self.artifact.module_id != "material_characterization"
            or self.artifact.artifact_type != "material_scientific_result"
        ):
            raise ContractError(
                "Constitutive reference must identify a Stage 03 material scientific result."
            )
        if self.artifact.provenance is None:
            raise ContractError("Constitutive reference requires artifact provenance.")

    @property
    def dependency(self) -> ArtifactDependency:
        """Reuse the V2 artifact ID/hash pair for downstream dependency checks."""

        return ArtifactDependency(self.artifact.artifact_id, self.artifact.content_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "model_id": self.model_id,
            "project_id": self.project_id,
            "design_revision": self.design_revision,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "artifact": self.artifact.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConstitutiveReference":
        mapping = ensure_mapping(data, name="ConstitutiveReference")
        reject_unknown_fields(
            mapping, dataclass_field_names(cls), name="ConstitutiveReference"
        )
        values = dict(mapping)
        values["artifact"] = ArtifactManifest.from_dict(
            dict(ensure_mapping(values.get("artifact"), name="constitutive artifact"))
        )
        return cls(**values)


@dataclass(frozen=True)
class MaterialDefinition:
    """Physical material identity, nominal strengths, and constitutive links."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    material_id: str
    source: str
    material_type: MaterialType
    nominal_strengths: dict[str, float]
    external_name: str | None = None
    units: dict[str, str] = field(default_factory=lambda: dict(_INTERNAL_UNITS))
    constitutive_references: tuple[ConstitutiveReference, ...] = ()

    def __post_init__(self) -> None:
        validate_schema_version(self.schema_version)
        validate_identifier(self.material_id, name="material_id")
        validate_identifier(self.source, name="source", semantic=True)
        object.__setattr__(
            self, "material_type", parse_enum(MaterialType, self.material_type, name="material_type")
        )
        if self.external_name is not None:
            validate_non_empty(self.external_name, name="external_name")

        if not isinstance(self.units, Mapping) or dict(self.units) != _INTERNAL_UNITS:
            raise UnitBoundaryError(
                "MaterialDefinition units must be exactly mm, MPa, and kN; "
                "convert at a V2 boundary before construction."
            )
        for key, quantity in (
            ("length", PhysicalQuantity.LENGTH),
            ("stress", PhysicalQuantity.STRESS),
            ("force", PhysicalQuantity.FORCE),
        ):
            BoundaryDefinition(
                physical_quantity=quantity,
                unit=self.units[key],
                sign_convention=SignConvention.NOT_APPLICABLE,
                reference_system=ReferenceSystem.SCALAR,
            )
        object.__setattr__(self, "units", dict(self.units))

        if not isinstance(self.nominal_strengths, Mapping):
            raise ContractError("nominal_strengths must be a mapping of named strengths.")
        strengths = dict(self.nominal_strengths)
        allowed = _STRENGTHS_BY_TYPE[self.material_type]
        required = "fc" if self.material_type is MaterialType.CONCRETE else "fy"
        if required not in strengths or set(strengths) - allowed:
            raise ContractError(
                f"{self.material_type.value} requires {required!r} and permits only "
                f"{sorted(allowed)!r} nominal strengths."
            )
        for name, value in strengths.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ContractError(f"nominal_strengths.{name} must be numeric in MPa.")
            strengths[name] = validate_positive(value, name=f"nominal_strengths.{name}")
        if "fu" in strengths and strengths["fu"] < strengths["fy"]:
            raise ContractError("Nominal fu must be greater than or equal to fy.")
        object.__setattr__(self, "nominal_strengths", strengths)

        references = tuple(self.constitutive_references)
        if not all(isinstance(item, ConstitutiveReference) for item in references):
            raise ContractError("constitutive_references must contain ConstitutiveReference items.")
        ensure_unique_ids((item.role for item in references), name="constitutive role")
        source_artifacts = [
            (
                item.project_id.casefold(),
                item.design_revision.casefold(),
                item.case_id.casefold(),
                item.run_id.casefold(),
                item.artifact.artifact_id.casefold(),
            )
            for item in references
        ]
        if len(source_artifacts) != len(set(source_artifacts)):
            raise ContractError("Duplicate constitutive artifact reference.")
        object.__setattr__(self, "constitutive_references", references)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "material_id": self.material_id,
            "source": self.source,
            "material_type": self.material_type.value,
            "nominal_strengths": dict(sorted(self.nominal_strengths.items())),
            "external_name": self.external_name,
            "units": dict(self.units),
            "constitutive_references": [
                item.to_dict() for item in self.constitutive_references
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialDefinition":
        mapping = ensure_mapping(data, name="MaterialDefinition")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="MaterialDefinition")
        values = dict(mapping)
        values["constitutive_references"] = tuple(
            ConstitutiveReference.from_dict(
                ensure_mapping(item, name="constitutive reference")
            )
            for item in values.get("constitutive_references", ())
        )
        return cls(**values)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "MaterialDefinition":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("MaterialDefinition JSON is invalid.") from exc
        return cls.from_dict(ensure_mapping(data, name="MaterialDefinition"))

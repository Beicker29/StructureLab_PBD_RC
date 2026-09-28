"""Explicit V2 boundaries for units, signs, and reference systems.

The conversion service in this module operates on copied boundary artifacts.
It does not alter native values or conventions inside V1 scientific kernels.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Iterable

from structurelab_pbd_rc.contracts._common import (
    V2_SCHEMA_VERSION,
    copy_json_mapping,
    dataclass_field_names,
    ensure_mapping,
    parse_enum,
    reject_unknown_fields,
    validate_identifier,
    validate_non_empty,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts._module_identity import MODULE_NUMBER_BY_ID
from structurelab_pbd_rc.contracts.artifacts import ArtifactDependency, ArtifactManifest
from structurelab_pbd_rc.core.exceptions import ContractError, UnitBoundaryError


class PhysicalQuantity(str, Enum):
    LENGTH = "length"
    FORCE = "force"
    CURVATURE = "curvature"
    ACCELERATION = "acceleration"
    STRESS = "stress"
    STRAIN = "strain"
    MOMENT = "moment"
    TIME = "time"


class SignConvention(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    UNSIGNED_NONNEGATIVE = "unsigned_nonnegative"
    TENSION_POSITIVE_COMPRESSION_NEGATIVE = "tension_positive_compression_negative"
    COMPRESSION_POSITIVE_TENSION_NEGATIVE = "compression_positive_tension_negative"
    POSITIVE_ALONG_AXIS = "positive_along_axis"
    NEGATIVE_ALONG_AXIS = "negative_along_axis"
    POSITIVE_ABOUT_AXIS = "positive_about_axis"
    NEGATIVE_ABOUT_AXIS = "negative_about_axis"


class ReferenceSystem(str, Enum):
    SCALAR = "scalar"
    MATERIAL = "material"
    SECTION_LOCAL = "section_local"
    ELEMENT_LOCAL = "element_local"
    STRUCTURE_GLOBAL = "structure_global"
    GEOGRAPHIC = "geographic"


@dataclass(frozen=True)
class _UnitDefinition:
    quantity: PhysicalQuantity
    to_si: float


STANDARD_GRAVITY_M_PER_S2 = 9.80665

_UNITS: dict[str, _UnitDefinition] = {
    "mm": _UnitDefinition(PhysicalQuantity.LENGTH, 1e-3),
    "cm": _UnitDefinition(PhysicalQuantity.LENGTH, 1e-2),
    "m": _UnitDefinition(PhysicalQuantity.LENGTH, 1.0),
    "N": _UnitDefinition(PhysicalQuantity.FORCE, 1.0),
    "kN": _UnitDefinition(PhysicalQuantity.FORCE, 1e3),
    "1/mm": _UnitDefinition(PhysicalQuantity.CURVATURE, 1e3),
    "1/m": _UnitDefinition(PhysicalQuantity.CURVATURE, 1.0),
    "m/s^2": _UnitDefinition(PhysicalQuantity.ACCELERATION, 1.0),
    "g": _UnitDefinition(PhysicalQuantity.ACCELERATION, STANDARD_GRAVITY_M_PER_S2),
    "Pa": _UnitDefinition(PhysicalQuantity.STRESS, 1.0),
    "kPa": _UnitDefinition(PhysicalQuantity.STRESS, 1e3),
    "MPa": _UnitDefinition(PhysicalQuantity.STRESS, 1e6),
    "1": _UnitDefinition(PhysicalQuantity.STRAIN, 1.0),
    "mm/mm": _UnitDefinition(PhysicalQuantity.STRAIN, 1.0),
    "m/m": _UnitDefinition(PhysicalQuantity.STRAIN, 1.0),
    "N-mm": _UnitDefinition(PhysicalQuantity.MOMENT, 1e-3),
    "kN-m": _UnitDefinition(PhysicalQuantity.MOMENT, 1e3),
    "s": _UnitDefinition(PhysicalQuantity.TIME, 1.0),
}


@dataclass(frozen=True)
class BoundaryDefinition:
    """Dimensional and directional meaning of values at a module boundary."""

    physical_quantity: PhysicalQuantity
    unit: str
    sign_convention: SignConvention
    reference_system: ReferenceSystem
    axis: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "physical_quantity",
            parse_enum(PhysicalQuantity, self.physical_quantity, name="physical_quantity"),
        )
        object.__setattr__(
            self,
            "sign_convention",
            parse_enum(SignConvention, self.sign_convention, name="sign_convention"),
        )
        object.__setattr__(
            self,
            "reference_system",
            parse_enum(ReferenceSystem, self.reference_system, name="reference_system"),
        )
        definition = _UNITS.get(self.unit)
        if definition is None:
            raise UnitBoundaryError(f"Unsupported boundary unit {self.unit!r}.")
        if definition.quantity is not self.physical_quantity:
            raise UnitBoundaryError(
                f"Unit {self.unit!r} represents {definition.quantity.value}, not "
                f"{self.physical_quantity.value}."
            )
        if self.axis is not None:
            validate_non_empty(self.axis, name="axis")
        if self.reference_system is ReferenceSystem.SCALAR and self.axis is not None:
            raise UnitBoundaryError("A scalar reference system cannot declare an axis.")
        if self.sign_convention in {
            SignConvention.POSITIVE_ALONG_AXIS,
            SignConvention.NEGATIVE_ALONG_AXIS,
            SignConvention.POSITIVE_ABOUT_AXIS,
            SignConvention.NEGATIVE_ABOUT_AXIS,
        } and self.axis is None:
            raise UnitBoundaryError(
                f"Sign convention {self.sign_convention.value!r} requires an axis."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "physical_quantity": self.physical_quantity.value,
            "unit": self.unit,
            "sign_convention": self.sign_convention.value,
            "reference_system": self.reference_system.value,
            "axis": self.axis,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundaryDefinition":
        reject_unknown_fields(data, dataclass_field_names(cls), name="BoundaryDefinition")
        return cls(**data)


@dataclass(frozen=True)
class ConversionRecord:
    """The complete, auditable transformation applied to boundary values."""

    conversion_id: str
    physical_quantity: PhysicalQuantity
    source_unit: str
    target_unit: str
    unit_factor: float
    source_sign_convention: SignConvention
    target_sign_convention: SignConvention
    sign_factor: float
    source_reference_system: ReferenceSystem
    target_reference_system: ReferenceSystem
    source_axis: str | None
    target_axis: str | None
    formula: str

    def __post_init__(self) -> None:
        validate_identifier(self.conversion_id, name="conversion_id")
        object.__setattr__(
            self,
            "physical_quantity",
            parse_enum(PhysicalQuantity, self.physical_quantity, name="physical_quantity"),
        )
        for field_name, enum_type in (
            ("source_sign_convention", SignConvention),
            ("target_sign_convention", SignConvention),
            ("source_reference_system", ReferenceSystem),
            ("target_reference_system", ReferenceSystem),
        ):
            object.__setattr__(
                self,
                field_name,
                parse_enum(enum_type, getattr(self, field_name), name=field_name),
            )
        for name in ("unit_factor", "sign_factor"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ContractError(f"{name} must be finite.")
            object.__setattr__(self, name, value)
        source_definition = _UNITS.get(self.source_unit)
        target_definition = _UNITS.get(self.target_unit)
        if source_definition is None or target_definition is None:
            raise UnitBoundaryError("ConversionRecord contains an unsupported unit.")
        if (
            source_definition.quantity is not self.physical_quantity
            or target_definition.quantity is not self.physical_quantity
        ):
            raise UnitBoundaryError(
                "ConversionRecord source and target units must match its physical quantity."
            )
        expected_unit_factor = source_definition.to_si / target_definition.to_si
        if not math.isclose(self.unit_factor, expected_unit_factor, rel_tol=1e-12, abs_tol=0.0):
            raise UnitBoundaryError(
                f"ConversionRecord unit_factor must be {expected_unit_factor!r}."
            )
        expected_sign_factor = _sign_factor(
            self.source_sign_convention,
            self.target_sign_convention,
        )
        if self.sign_factor != expected_sign_factor:
            raise UnitBoundaryError(
                f"ConversionRecord sign_factor must be {expected_sign_factor!r}."
            )
        if (
            self.source_reference_system is not self.target_reference_system
            or self.source_axis != self.target_axis
        ):
            raise UnitBoundaryError(
                "ConversionRecord cannot imply an undeclared coordinate transformation."
            )
        validate_non_empty(self.formula, name="formula")

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversion_id": self.conversion_id,
            "physical_quantity": self.physical_quantity.value,
            "source_unit": self.source_unit,
            "target_unit": self.target_unit,
            "unit_factor": self.unit_factor,
            "source_sign_convention": self.source_sign_convention.value,
            "target_sign_convention": self.target_sign_convention.value,
            "sign_factor": self.sign_factor,
            "source_reference_system": self.source_reference_system.value,
            "target_reference_system": self.target_reference_system.value,
            "source_axis": self.source_axis,
            "target_axis": self.target_axis,
            "formula": self.formula,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversionRecord":
        reject_unknown_fields(data, dataclass_field_names(cls), name="ConversionRecord")
        return cls(**data)


@dataclass(frozen=True)
class BoundaryArtifact:
    """Explicit V2 artifact containing native or converted boundary values."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    artifact_id: str
    module_id: str
    stage_number: str
    boundary: BoundaryDefinition
    values: tuple[float, ...]
    source_dependency: ArtifactDependency | None = None
    conversion: ConversionRecord | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_schema_version(self.schema_version)
        validate_identifier(self.artifact_id, name="artifact_id")
        validate_identifier(self.module_id, name="module_id", semantic=True)
        expected_number = MODULE_NUMBER_BY_ID.get(self.module_id)
        if expected_number is None or self.stage_number != expected_number:
            raise ContractError(
                f"Invalid V2 module identity {self.stage_number!r}/{self.module_id!r}."
            )
        numeric_values = tuple(float(value) for value in self.values)
        if not numeric_values or not all(math.isfinite(value) for value in numeric_values):
            raise ContractError("BoundaryArtifact values must be a non-empty finite sequence.")
        if (
            self.boundary.sign_convention is SignConvention.UNSIGNED_NONNEGATIVE
            and any(value < 0 for value in numeric_values)
        ):
            raise UnitBoundaryError("unsigned_nonnegative boundary values cannot be negative.")
        object.__setattr__(self, "values", numeric_values)
        if (self.source_dependency is None) != (self.conversion is None):
            raise ContractError(
                "A converted BoundaryArtifact requires both source_dependency and conversion."
            )
        if self.conversion is not None:
            if self.conversion.physical_quantity is not self.boundary.physical_quantity:
                raise UnitBoundaryError("Conversion quantity does not match artifact boundary.")
            if self.conversion.target_unit != self.boundary.unit:
                raise UnitBoundaryError("Conversion target unit does not match artifact boundary.")
            if self.conversion.target_sign_convention is not self.boundary.sign_convention:
                raise UnitBoundaryError(
                    "Conversion target sign convention does not match artifact boundary."
                )
            if (
                self.conversion.target_reference_system is not self.boundary.reference_system
                or self.conversion.target_axis != self.boundary.axis
            ):
                raise UnitBoundaryError(
                    "Conversion target reference system does not match artifact boundary."
                )
        object.__setattr__(
            self, "metadata", copy_json_mapping(self.metadata, name="BoundaryArtifact.metadata")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "module_id": self.module_id,
            "stage_number": self.stage_number,
            "artifact_type": "boundary_quantity",
            "boundary": self.boundary.to_dict(),
            "values": list(self.values),
            "source_dependency": (
                self.source_dependency.to_dict() if self.source_dependency is not None else None
            ),
            "conversion": self.conversion.to_dict() if self.conversion is not None else None,
            "metadata": copy_json_mapping(self.metadata, name="BoundaryArtifact.metadata"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoundaryArtifact":
        mapping = dict(ensure_mapping(data, name="BoundaryArtifact"))
        artifact_type = mapping.pop("artifact_type", "boundary_quantity")
        if artifact_type != "boundary_quantity":
            raise ContractError(f"Unsupported boundary artifact_type {artifact_type!r}.")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="BoundaryArtifact")
        validate_schema_version(mapping.get("schema_version"))
        mapping["boundary"] = BoundaryDefinition.from_dict(
            dict(ensure_mapping(mapping.get("boundary"), name="boundary"))
        )
        source = mapping.get("source_dependency")
        mapping["source_dependency"] = (
            ArtifactDependency.from_dict(dict(ensure_mapping(source, name="source_dependency")))
            if source is not None
            else None
        )
        conversion = mapping.get("conversion")
        mapping["conversion"] = (
            ConversionRecord.from_dict(dict(ensure_mapping(conversion, name="conversion")))
            if conversion is not None
            else None
        )
        mapping["values"] = tuple(mapping.get("values", ()))
        return cls(**mapping)

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(
            self.to_dict(),
            indent=indent,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":") if indent is None else None,
            allow_nan=False,
        )

    @classmethod
    def from_json(cls, value: str) -> "BoundaryArtifact":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("BoundaryArtifact JSON is invalid.") from exc
        return cls.from_dict(dict(ensure_mapping(data, name="BoundaryArtifact")))

    def serialized_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.serialized_bytes()).hexdigest()

    def to_manifest(self, *, uri: str, producer: str) -> ArtifactManifest:
        dependency = (self.source_dependency,) if self.source_dependency is not None else ()
        metadata = {
            **self.metadata,
            "physical_quantity": self.boundary.physical_quantity.value,
        }
        if self.conversion is not None:
            metadata["conversion"] = self.conversion.to_dict()
        return ArtifactManifest(
            schema_version=self.schema_version,
            artifact_id=self.artifact_id,
            artifact_type="boundary_quantity",
            module_id=self.module_id,
            stage_number=self.stage_number,
            producer=producer,
            uri=uri,
            sha256=self.sha256,
            units={"value": self.boundary.unit},
            sign_conventions={"value": self.boundary.sign_convention.value},
            axes={
                "reference_system": self.boundary.reference_system.value,
                "axis": self.boundary.axis or "not_applicable",
            },
            dependencies=dependency,
            metadata=metadata,
        )


def _unit_factor(source: BoundaryDefinition, target: BoundaryDefinition) -> float:
    if source.physical_quantity is not target.physical_quantity:
        raise UnitBoundaryError(
            f"Cannot convert {source.physical_quantity.value} to "
            f"{target.physical_quantity.value}."
        )
    return _UNITS[source.unit].to_si / _UNITS[target.unit].to_si


_OPPOSITE_SIGNS = {
    frozenset(
        {
            SignConvention.TENSION_POSITIVE_COMPRESSION_NEGATIVE,
            SignConvention.COMPRESSION_POSITIVE_TENSION_NEGATIVE,
        }
    ),
    frozenset({SignConvention.POSITIVE_ALONG_AXIS, SignConvention.NEGATIVE_ALONG_AXIS}),
    frozenset({SignConvention.POSITIVE_ABOUT_AXIS, SignConvention.NEGATIVE_ABOUT_AXIS}),
}


def _sign_factor(source: SignConvention, target: SignConvention) -> float:
    if source is target:
        return 1.0
    if frozenset({source, target}) in _OPPOSITE_SIGNS:
        return -1.0
    raise UnitBoundaryError(
        f"Sign convention {source.value!r} cannot be converted to {target.value!r}."
    )


def convert_boundary_artifact(
    source: BoundaryArtifact,
    target_boundary: BoundaryDefinition,
    *,
    artifact_id: str,
    conversion_id: str,
    module_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> BoundaryArtifact:
    """Create a new traced artifact; never mutate or relabel the source."""

    if (
        source.boundary.reference_system is not target_boundary.reference_system
        or source.boundary.axis != target_boundary.axis
    ):
        raise UnitBoundaryError(
            "Coordinate-system or axis changes require a future explicit coordinate transform."
        )
    unit_factor = _unit_factor(source.boundary, target_boundary)
    sign_factor = _sign_factor(
        source.boundary.sign_convention,
        target_boundary.sign_convention,
    )
    conversion = ConversionRecord(
        conversion_id=conversion_id,
        physical_quantity=source.boundary.physical_quantity,
        source_unit=source.boundary.unit,
        target_unit=target_boundary.unit,
        unit_factor=unit_factor,
        source_sign_convention=source.boundary.sign_convention,
        target_sign_convention=target_boundary.sign_convention,
        sign_factor=sign_factor,
        source_reference_system=source.boundary.reference_system,
        target_reference_system=target_boundary.reference_system,
        source_axis=source.boundary.axis,
        target_axis=target_boundary.axis,
        formula="target_value = source_value * unit_factor * sign_factor",
    )
    producer_module = module_id or source.module_id
    stage_number = MODULE_NUMBER_BY_ID.get(producer_module)
    if stage_number is None:
        raise ContractError(f"Unknown V2 module_id {producer_module!r}.")
    converted_metadata = {"converted_from_artifact_id": source.artifact_id}
    if metadata:
        converted_metadata.update(metadata)
    return BoundaryArtifact(
        schema_version=source.schema_version,
        artifact_id=artifact_id,
        module_id=producer_module,
        stage_number=stage_number,
        boundary=target_boundary,
        values=tuple(value * unit_factor * sign_factor for value in source.values),
        source_dependency=ArtifactDependency(source.artifact_id, source.sha256),
        conversion=conversion,
        metadata=converted_metadata,
    )


def convert_values(
    values: Iterable[float],
    source_boundary: BoundaryDefinition,
    target_boundary: BoundaryDefinition,
    *,
    source_artifact_id: str,
    converted_artifact_id: str,
    conversion_id: str,
    module_id: str,
) -> BoundaryArtifact:
    """Convenience boundary that still creates source and converted identities."""

    stage_number = MODULE_NUMBER_BY_ID.get(module_id)
    if stage_number is None:
        raise ContractError(f"Unknown V2 module_id {module_id!r}.")
    source = BoundaryArtifact(
        schema_version=V2_SCHEMA_VERSION,
        artifact_id=source_artifact_id,
        module_id=module_id,
        stage_number=stage_number,
        boundary=source_boundary,
        values=tuple(values),
    )
    return convert_boundary_artifact(
        source,
        target_boundary,
        artifact_id=converted_artifact_id,
        conversion_id=conversion_id,
    )


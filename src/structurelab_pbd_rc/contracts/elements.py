"""Solver-neutral element identity and section force resultants (Front 2 / 1C)."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
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
    validate_schema_version,
)
from structurelab_pbd_rc.contracts.boundaries import (
    BoundaryDefinition,
    PhysicalQuantity,
    ReferenceSystem,
    SignConvention,
)
from structurelab_pbd_rc.contracts.provenance import ProcessProvenance
from structurelab_pbd_rc.core.exceptions import ContractError, DependencyError, UnitBoundaryError


class ElementType(str, Enum):
    BEAM = "beam"
    COLUMN = "column"
    WALL = "wall"


_FORCE_UNITS = {"force": "kN", "moment": "kN-m"}
_AXES = {"P": "x", "Vy": "y", "Vz": "z", "T": "x", "My": "y", "Mz": "z"}
_SIGNS = {
    "P": SignConvention.COMPRESSION_POSITIVE_TENSION_NEGATIVE.value,
    "Vy": SignConvention.POSITIVE_ALONG_AXIS.value,
    "Vz": SignConvention.POSITIVE_ALONG_AXIS.value,
    "T": SignConvention.POSITIVE_ABOUT_AXIS.value,
    "My": SignConvention.POSITIVE_ABOUT_AXIS.value,
    "Mz": SignConvention.POSITIVE_ABOUT_AXIS.value,
}
_RESULTANTS = ("P", "Vy", "Vz", "T", "My", "Mz")


def _required(mapping: Mapping[str, Any], names: set[str], *, name: str) -> None:
    missing = sorted(names - mapping.keys())
    if missing:
        raise ContractError(f"{name} is missing required fields: {', '.join(missing)}.")


def _finite_number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ContractError(f"{name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ContractError(f"{name} must be a finite number.")
    return number


@dataclass(frozen=True)
class StructuralElementRef:
    """An element's stable identity, independent of its definitive section assignment."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    element_id: str
    source: str
    element_type: ElementType
    external_name: str | None = None
    story: str | None = None
    external_section_name: str | None = None

    def __post_init__(self) -> None:
        validate_schema_version(self.schema_version)
        validate_identifier(self.element_id, name="element_id")
        validate_identifier(self.source, name="source", semantic=True)
        object.__setattr__(
            self, "element_type", parse_enum(ElementType, self.element_type, name="element_type")
        )
        for name in ("external_name", "story", "external_section_name"):
            if getattr(self, name) is not None:
                validate_non_empty(getattr(self, name), name=name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "element_id": self.element_id,
            "source": self.source,
            "element_type": self.element_type.value,
            "external_name": self.external_name,
            "story": self.story,
            "external_section_name": self.external_section_name,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StructuralElementRef:
        mapping = ensure_mapping(data, name="StructuralElementRef")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="StructuralElementRef")
        _required(
            mapping,
            {"schema_version", "element_id", "source", "element_type"},
            name="StructuralElementRef",
        )
        return cls(**dict(mapping))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> StructuralElementRef:
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("StructuralElementRef JSON is invalid.") from exc
        return cls.from_dict(ensure_mapping(data, name="StructuralElementRef"))


@dataclass(frozen=True)
class NormalizedStation:
    """Dimensionless position: 0 is element end I, 1 is element end J."""

    value: float
    kind: str = "normalized"

    def __post_init__(self) -> None:
        if self.kind != "normalized":
            raise ContractError("station.kind must be 'normalized'; distance stations are unsupported.")
        number = _finite_number(self.value, name="station.value")
        if not 0.0 <= number <= 1.0:
            raise ContractError("station.value must be between 0.0 (I) and 1.0 (J).")
        object.__setattr__(self, "value", number)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NormalizedStation:
        mapping = ensure_mapping(data, name="NormalizedStation")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="NormalizedStation")
        _required(mapping, {"kind", "value"}, name="NormalizedStation")
        return cls(**dict(mapping))


@dataclass(frozen=True)
class SectionForceState:
    """Signed local resultants acting on the positive-x section cut face."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    element_id: str
    station: NormalizedStation
    P: float
    Vy: float
    Vz: float
    T: float
    My: float
    Mz: float
    load_case: str | None = None
    load_combination: str | None = None
    units: dict[str, str] = field(default_factory=lambda: dict(_FORCE_UNITS))
    axes: dict[str, str] = field(default_factory=lambda: dict(_AXES))
    sign_conventions: dict[str, str] = field(default_factory=lambda: dict(_SIGNS))
    action_face: str = "positive_x_cut_face"
    provenance: ProcessProvenance | None = None

    def __post_init__(self) -> None:
        validate_schema_version(self.schema_version)
        validate_identifier(self.element_id, name="element_id")
        if not isinstance(self.station, NormalizedStation):
            raise ContractError("station must be a tagged NormalizedStation.")
        if self.load_case is None and self.load_combination is None:
            raise ContractError("SectionForceState requires load_case and/or load_combination.")
        for name in ("load_case", "load_combination"):
            label = getattr(self, name)
            if label is not None:
                validate_non_empty(label, name=name)
                if label != label.strip():
                    raise ContractError(f"{name} must not contain surrounding whitespace.")
        for name in _RESULTANTS:
            object.__setattr__(self, name, _finite_number(getattr(self, name), name=name))

        if not isinstance(self.units, Mapping) or dict(self.units) != _FORCE_UNITS:
            raise UnitBoundaryError("SectionForceState units must be kN and kN-m.")
        if not isinstance(self.axes, Mapping) or dict(self.axes) != _AXES:
            raise UnitBoundaryError("SectionForceState axes must be the declared local x-y-z axes.")
        if not isinstance(self.sign_conventions, Mapping) or dict(self.sign_conventions) != _SIGNS:
            raise UnitBoundaryError("SectionForceState sign conventions must be the declared internal ones.")
        if self.action_face != "positive_x_cut_face":
            raise UnitBoundaryError("SectionForceState resultants must act on the positive-x cut face.")
        object.__setattr__(self, "units", dict(self.units))
        object.__setattr__(self, "axes", dict(self.axes))
        object.__setattr__(self, "sign_conventions", dict(self.sign_conventions))
        for name in _RESULTANTS:
            is_force = name in {"P", "Vy", "Vz"}
            BoundaryDefinition(
                physical_quantity=PhysicalQuantity.FORCE if is_force else PhysicalQuantity.MOMENT,
                unit=self.units["force" if is_force else "moment"],
                sign_convention=self.sign_conventions[name],
                reference_system=ReferenceSystem.ELEMENT_LOCAL,
                axis=self.axes[name],
            )

        if self.provenance is not None:
            if not isinstance(self.provenance, ProcessProvenance):
                raise ContractError("provenance must be a ProcessProvenance.")
            for name, expected in self.units.items():
                actual = self.provenance.units.get(name)
                if actual is not None and actual != expected:
                    raise UnitBoundaryError(f"provenance.units.{name} conflicts with SectionForceState.")
            for name, expected in self.sign_conventions.items():
                actual = self.provenance.sign_conventions.get(name)
                if actual is not None and actual != expected:
                    raise UnitBoundaryError(
                        f"provenance.sign_conventions.{name} conflicts with SectionForceState."
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "element_id": self.element_id,
            "load_case": self.load_case,
            "load_combination": self.load_combination,
            "station": self.station.to_dict(),
            **{name: getattr(self, name) for name in _RESULTANTS},
            "units": dict(self.units),
            "axes": dict(self.axes),
            "sign_conventions": dict(self.sign_conventions),
            "action_face": self.action_face,
            "provenance": self.provenance.to_dict() if self.provenance is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SectionForceState:
        mapping = ensure_mapping(data, name="SectionForceState")
        reject_unknown_fields(mapping, dataclass_field_names(cls), name="SectionForceState")
        _required(
            mapping,
            {
                "schema_version", "element_id", "station", *_RESULTANTS,
                "units", "axes", "sign_conventions", "action_face",
            },
            name="SectionForceState",
        )
        values = dict(mapping)
        values["station"] = NormalizedStation.from_dict(
            ensure_mapping(values["station"], name="station")
        )
        if values.get("provenance") is not None:
            values["provenance"] = ProcessProvenance.from_dict(
                dict(ensure_mapping(values["provenance"], name="provenance"))
            )
        return cls(**values)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> SectionForceState:
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("SectionForceState JSON is invalid.") from exc
        return cls.from_dict(ensure_mapping(data, name="SectionForceState"))


def validate_section_force_states(
    states: Iterable[SectionForceState],
    *,
    elements: Iterable[StructuralElementRef] | None = None,
) -> None:
    """Reject duplicate case/combination/station keys and unresolved elements."""

    values = tuple(states)
    if not all(isinstance(item, SectionForceState) for item in values):
        raise ContractError("states must contain SectionForceState items.")
    keys = [
        (
            item.element_id.casefold(),
            item.load_case.casefold() if item.load_case is not None else None,
            item.load_combination.casefold() if item.load_combination is not None else None,
            item.station.value,
        )
        for item in values
    ]
    if len(keys) != len(set(keys)):
        raise ContractError("Duplicate SectionForceState for element, load, and station.")
    if elements is not None:
        refs = tuple(elements)
        if not all(isinstance(item, StructuralElementRef) for item in refs):
            raise ContractError("elements must contain StructuralElementRef items.")
        ensure_unique_ids((item.element_id for item in refs), name="element_id")
        known = {item.element_id.casefold() for item in refs}
        for item in values:
            if item.element_id.casefold() not in known:
                raise DependencyError(f"Unknown element_id {item.element_id!r} in SectionForceState.")

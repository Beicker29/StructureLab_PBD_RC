"""Solver-neutral geometry and reinforcement for a physical RC section."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from structurelab_pbd_rc.contracts._common import (
    V2_SCHEMA_VERSION,
    ensure_mapping,
    ensure_unique_ids,
    parse_enum,
    reject_unknown_fields,
    validate_identifier,
    validate_non_empty,
    validate_positive,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts.boundaries import (
    BoundaryDefinition,
    PhysicalQuantity,
    ReferenceSystem,
    SignConvention,
)
from structurelab_pbd_rc.contracts.materials import MaterialDefinition, MaterialType
from structurelab_pbd_rc.core.exceptions import ContractError, DependencyError, UnitBoundaryError


_SECTION_UNITS = {"length": "mm", "area": "mm^2", "stress": "MPa", "force": "kN"}


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


def _positive_number(value: object, *, name: str) -> float:
    return validate_positive(_finite_number(value, name=name), name=name)


def _positive_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{name} must be a positive integer.")
    return value


def _required(mapping: Mapping[str, Any], names: set[str], *, name: str) -> None:
    missing = sorted(names - mapping.keys())
    if missing:
        raise ContractError(f"{name} is missing required fields: {', '.join(missing)}.")


class SectionType(str, Enum):
    REINFORCED_CONCRETE = "reinforced_concrete"


@dataclass(frozen=True)
class SectionCoordinateSystem:
    """Canonical local y-z view, with longitudinal x reserved for the element."""

    origin: str = "gross_geometry_centroid"
    longitudinal_axis: str = "x"
    view_direction: str = "from_positive_x_toward_origin"
    positive_y: str = "right"
    positive_z: str = "up"

    def __post_init__(self) -> None:
        expected = {
            "origin": "gross_geometry_centroid",
            "longitudinal_axis": "x",
            "view_direction": "from_positive_x_toward_origin",
            "positive_y": "right",
            "positive_z": "up",
        }
        if self.to_dict() != expected:
            raise ContractError(
                "Only the declared local y-z convention with the gross centroid at "
                "(0, 0) is supported; transform external axes at a V2 boundary."
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "origin": self.origin,
            "longitudinal_axis": self.longitudinal_axis,
            "view_direction": self.view_direction,
            "positive_y": self.positive_y,
            "positive_z": self.positive_z,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SectionCoordinateSystem":
        mapping = ensure_mapping(data, name="SectionCoordinateSystem")
        reject_unknown_fields(mapping, set(cls.__dataclass_fields__), name="SectionCoordinateSystem")
        _required(
            mapping,
            {"origin", "longitudinal_axis", "view_direction", "positive_y", "positive_z"},
            name="SectionCoordinateSystem",
        )
        return cls(**mapping)


@dataclass(frozen=True)
class RectangleGeometry:
    """A tagged rectangle in the local y-z plane; later shapes get new tags."""

    y_min_mm: float
    y_max_mm: float
    z_min_mm: float
    z_max_mm: float

    def __post_init__(self) -> None:
        for name in ("y_min_mm", "y_max_mm", "z_min_mm", "z_max_mm"):
            object.__setattr__(self, name, _finite_number(getattr(self, name), name=name))
        if self.y_max_mm <= self.y_min_mm or self.z_max_mm <= self.z_min_mm:
            raise ContractError("Rectangle dimensions in y and z must be positive.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometry_type": "rectangle",
            "y_min_mm": self.y_min_mm,
            "y_max_mm": self.y_max_mm,
            "z_min_mm": self.z_min_mm,
            "z_max_mm": self.z_max_mm,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RectangleGeometry":
        mapping = ensure_mapping(data, name="RectangleGeometry")
        reject_unknown_fields(
            mapping,
            {"geometry_type", "y_min_mm", "y_max_mm", "z_min_mm", "z_max_mm"},
            name="RectangleGeometry",
        )
        if mapping.get("geometry_type") != "rectangle":
            raise ContractError("Unsupported section geometry_type; only 'rectangle' exists in 1B.")
        _required(
            mapping,
            {"y_min_mm", "y_max_mm", "z_min_mm", "z_max_mm"},
            name="RectangleGeometry",
        )
        return cls(**{key: mapping[key] for key in ("y_min_mm", "y_max_mm", "z_min_mm", "z_max_mm")})


def _contains(outer: RectangleGeometry, inner: RectangleGeometry, *, strict: bool) -> bool:
    if strict:
        return (
            outer.y_min_mm < inner.y_min_mm < inner.y_max_mm < outer.y_max_mm
            and outer.z_min_mm < inner.z_min_mm < inner.z_max_mm < outer.z_max_mm
        )
    return (
        outer.y_min_mm <= inner.y_min_mm < inner.y_max_mm <= outer.y_max_mm
        and outer.z_min_mm <= inner.z_min_mm < inner.z_max_mm <= outer.z_max_mm
    )


def _overlap(a: RectangleGeometry, b: RectangleGeometry) -> bool:
    return (
        max(a.y_min_mm, b.y_min_mm) < min(a.y_max_mm, b.y_max_mm)
        and max(a.z_min_mm, b.z_min_mm) < min(a.z_max_mm, b.z_max_mm)
    )


@dataclass(frozen=True)
class RectangularRegionGeometry:
    """A rectangular domain with explicit rectangular voids, not fibers."""

    outer: RectangleGeometry
    voids: tuple[RectangleGeometry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.outer, RectangleGeometry):
            raise ContractError("Region outer geometry must be a rectangle in 1B.")
        if not isinstance(self.voids, (tuple, list)) or not all(
            isinstance(item, RectangleGeometry) for item in self.voids
        ):
            raise ContractError("Region voids must be rectangular geometries.")
        voids = tuple(self.voids)
        for index, void in enumerate(voids):
            if not _contains(self.outer, void, strict=True):
                raise ContractError("A region void must lie strictly inside its outer geometry.")
            if any(_overlap(void, previous) for previous in voids[:index]):
                raise ContractError("Region voids cannot overlap.")
        object.__setattr__(self, "voids", voids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometry_type": "rectangular_domain",
            "outer": self.outer.to_dict(),
            "voids": [item.to_dict() for item in self.voids],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RectangularRegionGeometry":
        mapping = ensure_mapping(data, name="RectangularRegionGeometry")
        reject_unknown_fields(
            mapping, {"geometry_type", "outer", "voids"}, name="RectangularRegionGeometry"
        )
        if mapping.get("geometry_type") != "rectangular_domain":
            raise ContractError("Unsupported region geometry_type in 1B.")
        _required(mapping, {"outer"}, name="RectangularRegionGeometry")
        voids = mapping.get("voids", ())
        if not isinstance(voids, (tuple, list)):
            raise ContractError("Region voids must be a sequence.")
        return cls(
            outer=RectangleGeometry.from_dict(
                ensure_mapping(mapping["outer"], name="region outer")
            ),
            voids=tuple(
                RectangleGeometry.from_dict(ensure_mapping(item, name="region void"))
                for item in voids
            ),
        )


@dataclass(frozen=True)
class ConcreteRegion:
    region_id: str
    role: str
    geometry: RectangularRegionGeometry
    material_id: str

    def __post_init__(self) -> None:
        validate_identifier(self.region_id, name="region_id")
        validate_identifier(self.role, name="region role", semantic=True)
        validate_identifier(self.material_id, name="region material_id")
        if not isinstance(self.geometry, RectangularRegionGeometry):
            raise ContractError("Concrete region requires a rectangular domain in 1B.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "role": self.role,
            "geometry": self.geometry.to_dict(),
            "material_id": self.material_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConcreteRegion":
        mapping = ensure_mapping(data, name="ConcreteRegion")
        reject_unknown_fields(
            mapping, {"region_id", "role", "geometry", "material_id"}, name="ConcreteRegion"
        )
        _required(mapping, {"region_id", "role", "geometry", "material_id"}, name="ConcreteRegion")
        values = dict(mapping)
        values["geometry"] = RectangularRegionGeometry.from_dict(
            ensure_mapping(values["geometry"], name="region geometry")
        )
        return cls(**values)


@dataclass(frozen=True)
class LongitudinalBar:
    y_mm: float
    z_mm: float
    area_mm2: float
    material_id: str
    bar_id: str | None = None

    def __post_init__(self) -> None:
        if self.bar_id is not None:
            validate_identifier(self.bar_id, name="bar_id")
        validate_identifier(self.material_id, name="bar material_id")
        object.__setattr__(self, "y_mm", _finite_number(self.y_mm, name="bar.y_mm"))
        object.__setattr__(self, "z_mm", _finite_number(self.z_mm, name="bar.z_mm"))
        object.__setattr__(self, "area_mm2", _positive_number(self.area_mm2, name="bar.area_mm2"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "bar_id": self.bar_id,
            "y_mm": self.y_mm,
            "z_mm": self.z_mm,
            "area_mm2": self.area_mm2,
            "material_id": self.material_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LongitudinalBar":
        mapping = ensure_mapping(data, name="LongitudinalBar")
        reject_unknown_fields(
            mapping, {"bar_id", "y_mm", "z_mm", "area_mm2", "material_id"},
            name="LongitudinalBar",
        )
        _required(mapping, {"y_mm", "z_mm", "area_mm2", "material_id"}, name="LongitudinalBar")
        return cls(**mapping)


class TransverseOrientation(str, Enum):
    Y = "y"
    Z = "z"
    BOTH = "both"


@dataclass(frozen=True)
class TransverseReinforcement:
    reinforcement_id: str
    material_id: str
    spacing_mm: float
    arrangement: str
    orientation: TransverseOrientation
    diameter_mm: float | None = None
    area_mm2: float | None = None
    legs_y: int | None = None
    legs_z: int | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.reinforcement_id, name="reinforcement_id")
        validate_identifier(self.material_id, name="transverse material_id")
        validate_identifier(self.arrangement, name="transverse arrangement", semantic=True)
        object.__setattr__(
            self, "orientation",
            parse_enum(TransverseOrientation, self.orientation, name="transverse orientation"),
        )
        object.__setattr__(
            self, "spacing_mm", _positive_number(self.spacing_mm, name="transverse.spacing_mm")
        )
        if (self.diameter_mm is None) == (self.area_mm2 is None):
            raise ContractError("Specify exactly one of transverse diameter_mm or area_mm2.")
        for name in ("diameter_mm", "area_mm2"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self, name, _positive_number(value, name=f"transverse.{name}")
                )
        active_y = self.orientation in (TransverseOrientation.Y, TransverseOrientation.BOTH)
        active_z = self.orientation in (TransverseOrientation.Z, TransverseOrientation.BOTH)
        for axis, active in (("y", active_y), ("z", active_z)):
            value = getattr(self, f"legs_{axis}")
            if active:
                _positive_int(value, name=f"transverse.legs_{axis}")
            elif value is not None:
                raise ContractError(f"transverse.legs_{axis} conflicts with orientation.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reinforcement_id": self.reinforcement_id,
            "material_id": self.material_id,
            "spacing_mm": self.spacing_mm,
            "arrangement": self.arrangement,
            "orientation": self.orientation.value,
            "diameter_mm": self.diameter_mm,
            "area_mm2": self.area_mm2,
            "legs_y": self.legs_y,
            "legs_z": self.legs_z,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TransverseReinforcement":
        mapping = ensure_mapping(data, name="TransverseReinforcement")
        reject_unknown_fields(mapping, set(cls.__dataclass_fields__), name="TransverseReinforcement")
        _required(
            mapping,
            {"reinforcement_id", "material_id", "spacing_mm", "arrangement", "orientation"},
            name="TransverseReinforcement",
        )
        return cls(**mapping)


@dataclass(frozen=True)
class SectionDefinition:
    """Physical section; neither a fiber mesh nor a constitutive computation."""

    SUPPORTED_SCHEMA_VERSION: ClassVar[str] = V2_SCHEMA_VERSION

    schema_version: str
    section_id: str
    source: str
    section_type: SectionType
    geometry: RectangleGeometry
    coordinate_system: SectionCoordinateSystem
    concrete_regions: tuple[ConcreteRegion, ...]
    longitudinal_bars: tuple[LongitudinalBar, ...]
    transverse_reinforcement: tuple[TransverseReinforcement, ...] = ()
    external_name: str | None = None
    units: dict[str, str] = field(default_factory=lambda: dict(_SECTION_UNITS))

    def __post_init__(self) -> None:
        validate_schema_version(self.schema_version)
        validate_identifier(self.section_id, name="section_id")
        validate_identifier(self.source, name="source", semantic=True)
        object.__setattr__(
            self, "section_type", parse_enum(SectionType, self.section_type, name="section_type")
        )
        if self.external_name is not None:
            validate_non_empty(self.external_name, name="external_name")
        if not isinstance(self.units, Mapping) or dict(self.units) != _SECTION_UNITS:
            raise UnitBoundaryError(
                "SectionDefinition units must be mm, mm^2, MPa, and kN; "
                "convert at a V2 boundary before construction."
            )
        for name, quantity in (
            ("length", PhysicalQuantity.LENGTH),
            ("stress", PhysicalQuantity.STRESS),
            ("force", PhysicalQuantity.FORCE),
        ):
            BoundaryDefinition(
                physical_quantity=quantity,
                unit=self.units[name],
                sign_convention=SignConvention.NOT_APPLICABLE,
                reference_system=ReferenceSystem.SCALAR,
            )
        object.__setattr__(self, "units", dict(self.units))

        if not isinstance(self.geometry, RectangleGeometry):
            raise ContractError("Only rectangular gross section geometry is supported in 1B.")
        if not isinstance(self.coordinate_system, SectionCoordinateSystem):
            raise ContractError("coordinate_system must be a SectionCoordinateSystem.")
        if not (
            math.isclose(self.geometry.y_min_mm, -self.geometry.y_max_mm, abs_tol=1e-9)
            and math.isclose(self.geometry.z_min_mm, -self.geometry.z_max_mm, abs_tol=1e-9)
        ):
            raise ContractError("Gross rectangle must be centered at the declared (0, 0) origin.")

        for name, cls in (
            ("concrete_regions", ConcreteRegion),
            ("longitudinal_bars", LongitudinalBar),
            ("transverse_reinforcement", TransverseReinforcement),
        ):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or not all(
                isinstance(item, cls) for item in values
            ):
                raise ContractError(f"{name} must contain {cls.__name__} items.")
            object.__setattr__(self, name, tuple(values))
        if not self.longitudinal_bars:
            raise ContractError("A reinforced concrete section requires longitudinal bars.")
        ensure_unique_ids((item.region_id for item in self.concrete_regions), name="region_id")
        ensure_unique_ids((item.role for item in self.concrete_regions), name="region role")
        ensure_unique_ids(
            (item.bar_id for item in self.longitudinal_bars if item.bar_id is not None),
            name="bar_id",
        )
        ensure_unique_ids(
            (item.reinforcement_id for item in self.transverse_reinforcement),
            name="reinforcement_id",
        )
        coordinates = [(item.y_mm, item.z_mm) for item in self.longitudinal_bars]
        if len(coordinates) != len(set(coordinates)):
            raise ContractError("Duplicate longitudinal bar coordinates.")
        for bar in self.longitudinal_bars:
            if not (
                self.geometry.y_min_mm <= bar.y_mm <= self.geometry.y_max_mm
                and self.geometry.z_min_mm <= bar.z_mm <= self.geometry.z_max_mm
            ):
                raise ContractError("Longitudinal bar lies outside the gross section geometry.")

        by_role = {item.role: item for item in self.concrete_regions}
        if set(by_role) != {"cover", "core"}:
            raise ContractError("A 1B RC section requires one cover and one core region.")
        cover = by_role["cover"].geometry
        core = by_role["core"].geometry
        if cover.outer != self.geometry or core.voids:
            raise ContractError("Cover must follow the gross outline and core must be solid.")
        if not _contains(self.geometry, core.outer, strict=True):
            raise ContractError("Core must lie strictly inside the gross section.")
        if cover.voids != (core.outer,):
            raise ContractError("Cover must exclude exactly the core geometry.")

    @property
    def material_ids(self) -> tuple[str, ...]:
        """IDs for explicit resolution against MaterialDefinition, without copying it."""

        return tuple(
            dict.fromkeys(
                item.material_id
                for group in (
                    self.concrete_regions,
                    self.longitudinal_bars,
                    self.transverse_reinforcement,
                )
                for item in group
            )
        )

    def validate_material_references(self, materials: Iterable[MaterialDefinition]) -> None:
        """Check supplied 1A identities and physical types; no constitutive evaluation."""

        values = tuple(materials)
        if not all(isinstance(item, MaterialDefinition) for item in values):
            raise ContractError("materials must contain MaterialDefinition items.")
        ensure_unique_ids((item.material_id for item in values), name="material_id")
        by_id = {item.material_id.casefold(): item for item in values}
        for group, expected_type in (
            (self.concrete_regions, MaterialType.CONCRETE),
            (self.longitudinal_bars, MaterialType.REINFORCING_STEEL),
            (self.transverse_reinforcement, MaterialType.REINFORCING_STEEL),
        ):
            for item in group:
                material = by_id.get(item.material_id.casefold())
                if material is None:
                    raise DependencyError(f"Unknown material_id {item.material_id!r}.")
                if material.material_type is not expected_type:
                    raise DependencyError(
                        f"material_id {item.material_id!r} requires {expected_type.value}."
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "section_id": self.section_id,
            "source": self.source,
            "section_type": self.section_type.value,
            "external_name": self.external_name,
            "units": dict(self.units),
            "coordinate_system": self.coordinate_system.to_dict(),
            "geometry": self.geometry.to_dict(),
            "concrete_regions": [item.to_dict() for item in self.concrete_regions],
            "longitudinal_bars": [item.to_dict() for item in self.longitudinal_bars],
            "transverse_reinforcement": [
                item.to_dict() for item in self.transverse_reinforcement
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SectionDefinition":
        mapping = ensure_mapping(data, name="SectionDefinition")
        reject_unknown_fields(
            mapping,
            {
                "schema_version", "section_id", "source", "section_type", "external_name",
                "units", "coordinate_system", "geometry", "concrete_regions",
                "longitudinal_bars", "transverse_reinforcement",
            },
            name="SectionDefinition",
        )
        _required(
            mapping,
            {
                "schema_version", "section_id", "source", "section_type",
                "units", "coordinate_system", "geometry", "concrete_regions",
                "longitudinal_bars",
            },
            name="SectionDefinition",
        )
        values = dict(mapping)
        values["coordinate_system"] = SectionCoordinateSystem.from_dict(
            ensure_mapping(values["coordinate_system"], name="coordinate_system")
        )
        values["geometry"] = RectangleGeometry.from_dict(
            ensure_mapping(values["geometry"], name="section geometry")
        )
        for name, cls_type in (
            ("concrete_regions", ConcreteRegion),
            ("longitudinal_bars", LongitudinalBar),
            ("transverse_reinforcement", TransverseReinforcement),
        ):
            items = values.get(name, ())
            if not isinstance(items, (tuple, list)):
                raise ContractError(f"{name} must be a sequence.")
            values[name] = tuple(
                cls_type.from_dict(ensure_mapping(item, name=name)) for item in items
            )
        return cls(**values)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "SectionDefinition":
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("SectionDefinition JSON is invalid.") from exc
        return cls.from_dict(ensure_mapping(data, name="SectionDefinition"))

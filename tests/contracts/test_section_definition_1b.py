"""Front 2 / 1B: physical section data without fibers or solver commands."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from structurelab_pbd_rc.contracts import (
    ArtifactManifest,
    ConcreteRegion,
    LongitudinalBar,
    MaterialDefinition,
    ProcessProvenance,
    RectangleGeometry,
    RectangularRegionGeometry,
    SectionCoordinateSystem,
    SectionDefinition,
    SectionType,
    TransverseReinforcement,
)
from structurelab_pbd_rc.core.exceptions import (
    ContractError,
    DependencyError,
    SchemaVersionError,
    UnitBoundaryError,
)


def gross() -> RectangleGeometry:
    return RectangleGeometry(-200, 200, -300, 300)


def core() -> RectangleGeometry:
    return RectangleGeometry(-160, 160, -260, 260)


def regions() -> tuple[ConcreteRegion, ConcreteRegion]:
    return (
        ConcreteRegion(
            region_id="cover_region",
            role="cover",
            geometry=RectangularRegionGeometry(gross(), (core(),)),
            material_id="CONC_UNCONF_28",
        ),
        ConcreteRegion(
            region_id="core_region",
            role="core",
            geometry=RectangularRegionGeometry(core()),
            material_id="CONC_CONF_28",
        ),
    )


def bars() -> tuple[LongitudinalBar, ...]:
    return (
        LongitudinalBar(-140, -240, 314, "STEEL_420", "bar_01"),
        LongitudinalBar(140, -240, 314, "STEEL_420", "bar_02"),
        LongitudinalBar(-140, 240, 314, "STEEL_420", "bar_03"),
        LongitudinalBar(140, 240, 314, "STEEL_420", "bar_04"),
    )


def ties(**changes: object) -> TransverseReinforcement:
    fields: dict[str, object] = {
        "reinforcement_id": "hoop_01",
        "material_id": "STEEL_TRANS_420",
        "diameter_mm": 10.0,
        "spacing_mm": 100.0,
        "arrangement": "closed_hoop",
        "orientation": "both",
        "legs_y": 2,
        "legs_z": 2,
    }
    fields.update(changes)
    return TransverseReinforcement(**fields)


def section(**changes: object) -> SectionDefinition:
    fields: dict[str, object] = {
        "schema_version": "2",
        "section_id": "COLUMN_400X600",
        "source": "structurelab",
        "section_type": SectionType.REINFORCED_CONCRETE,
        "geometry": gross(),
        "coordinate_system": SectionCoordinateSystem(),
        "concrete_regions": regions(),
        "longitudinal_bars": bars(),
        "transverse_reinforcement": (ties(),),
    }
    fields.update(changes)
    return SectionDefinition(**fields)


def materials() -> tuple[MaterialDefinition, ...]:
    return (
        MaterialDefinition("2", "CONC_UNCONF_28", "structurelab", "concrete", {"fc": 28}),
        MaterialDefinition("2", "CONC_CONF_28", "structurelab", "concrete", {"fc": 28}),
        MaterialDefinition("2", "STEEL_420", "structurelab", "reinforcing_steel", {"fy": 420}),
        MaterialDefinition("2", "STEEL_TRANS_420", "structurelab", "reinforcing_steel", {"fy": 420}),
    )


def test_valid_reinforced_concrete_rectangle_uses_local_y_z() -> None:
    value = section()
    assert value.section_type is SectionType.REINFORCED_CONCRETE
    assert value.geometry.y_max_mm - value.geometry.y_min_mm == 400
    assert value.geometry.z_max_mm - value.geometry.z_min_mm == 600
    assert value.units == {
        "length": "mm", "area": "mm^2", "stress": "MPa", "force": "kN"
    }
    assert value.coordinate_system.origin == "gross_geometry_centroid"
    assert value.coordinate_system.longitudinal_axis == "x"
    assert value.coordinate_system.positive_y == "right"
    assert value.coordinate_system.positive_z == "up"
    assert value.material_ids == (
        "CONC_UNCONF_28", "CONC_CONF_28", "STEEL_420", "STEEL_TRANS_420"
    )


def test_external_name_preserves_etabs_label_without_becoming_identity() -> None:
    value = section(source="etabs", external_name="C400x600 - Level 3")
    assert value.section_id == "COLUMN_400X600"
    assert value.external_name == "C400x600 - Level 3"
    assert value.to_dict()["source"] == "etabs"


def test_external_name_is_optional_and_blank_name_rejected() -> None:
    assert section().external_name is None
    with pytest.raises(ContractError, match="external_name"):
        section(external_name="  ")


def test_each_longitudinal_bar_has_explicit_coordinates_area_and_material() -> None:
    value = section()
    assert len(value.longitudinal_bars) == 4
    assert {(bar.y_mm, bar.z_mm) for bar in value.longitudinal_bars} == {
        (-140, -240), (140, -240), (-140, 240), (140, 240)
    }
    assert all(bar.area_mm2 == 314 for bar in value.longitudinal_bars)
    assert all(bar.material_id == "STEEL_420" for bar in value.longitudinal_bars)
    anonymous = replace(value.longitudinal_bars[0], bar_id=None)
    assert section(longitudinal_bars=(anonymous, *bars()[1:])).longitudinal_bars[0].bar_id is None


def test_cover_is_gross_rectangle_minus_solid_core() -> None:
    cover, core_region = section().concrete_regions
    assert cover.role == "cover" and core_region.role == "core"
    assert cover.geometry.outer == gross()
    assert cover.geometry.voids == (core(),)
    assert core_region.geometry.outer == core()
    assert core_region.geometry.voids == ()
    assert cover.material_id != core_region.material_id


def test_transverse_hoop_records_geometry_but_is_not_a_longitudinal_bar() -> None:
    value = section()
    hoop = value.transverse_reinforcement[0]
    assert (hoop.material_id, hoop.diameter_mm, hoop.spacing_mm) == (
        "STEEL_TRANS_420", 10.0, 100.0
    )
    assert (hoop.arrangement, hoop.orientation.value, hoop.legs_y, hoop.legs_z) == (
        "closed_hoop", "both", 2, 2
    )
    assert len(value.longitudinal_bars) == 4
    area_option = ties(diameter_mm=None, area_mm2=78.54)
    assert area_option.area_mm2 == 78.54


@pytest.mark.parametrize(
    "bounds",
    [(0, 0, -300, 300), (-200, 200, 1, 1), (10, -10, -300, 300), (float("nan"), 200, -300, 300), ("-200", 200, -300, 300)],
)
def test_invalid_rectangle_dimensions_or_coordinates_are_rejected(bounds: tuple[object, ...]) -> None:
    with pytest.raises(ContractError):
        RectangleGeometry(*bounds)


@pytest.mark.parametrize("area", [0, -1, float("inf"), True, "314"])
def test_invalid_longitudinal_area_is_rejected(area: object) -> None:
    with pytest.raises(ContractError, match="area_mm2"):
        LongitudinalBar(0, 0, area, "STEEL_420")


@pytest.mark.parametrize("coordinate", [None, "10", float("nan"), float("inf"), True])
def test_non_numeric_or_nonfinite_bar_coordinate_is_rejected(coordinate: object) -> None:
    with pytest.raises(ContractError, match="bar.y_mm"):
        LongitudinalBar(coordinate, 0, 314, "STEEL_420")


def test_empty_material_references_and_unresolved_ids_are_rejected() -> None:
    with pytest.raises(ContractError, match="material_id"):
        replace(bars()[0], material_id="")
    with pytest.raises(ContractError, match="material_id"):
        replace(regions()[0], material_id="")
    with pytest.raises(ContractError, match="material_id"):
        ties(material_id="")
    section().validate_material_references(materials())
    with pytest.raises(DependencyError, match="Unknown material_id"):
        section().validate_material_references(materials()[:-1])
    wrong_type = replace(materials()[0], material_type="reinforcing_steel", nominal_strengths={"fy": 420})
    with pytest.raises(DependencyError, match="requires concrete"):
        section().validate_material_references((wrong_type, *materials()[1:]))


def test_obviously_inconsistent_cover_and_core_are_rejected() -> None:
    cover, core_region = regions()
    with pytest.raises(ContractError, match="Core must lie strictly"):
        section(
            concrete_regions=(
                cover,
                replace(core_region, geometry=RectangularRegionGeometry(RectangleGeometry(-210, 210, -260, 260))),
            )
        )
    with pytest.raises(ContractError, match="Cover must exclude"):
        section(concrete_regions=(replace(cover, geometry=RectangularRegionGeometry(gross())), core_region))
    with pytest.raises(ContractError, match="Cover must follow"):
        section(concrete_regions=(replace(cover, geometry=RectangularRegionGeometry(core())), core_region))
    with pytest.raises(ContractError, match="centered"):
        section(geometry=RectangleGeometry(-190, 210, -300, 300))


def test_bar_outside_section_and_duplicate_bars_or_regions_are_rejected() -> None:
    with pytest.raises(ContractError, match="outside"):
        section(longitudinal_bars=(replace(bars()[0], y_mm=250), *bars()[1:]))
    with pytest.raises(ContractError, match="Duplicate bar_id"):
        section(longitudinal_bars=(bars()[0], replace(bars()[1], bar_id="BAR_01"), *bars()[2:]))
    with pytest.raises(ContractError, match="Duplicate longitudinal bar coordinates"):
        section(longitudinal_bars=(bars()[0], replace(bars()[1], y_mm=-140, z_mm=-240), *bars()[2:]))
    with pytest.raises(ContractError, match="Duplicate region_id"):
        section(concrete_regions=(regions()[0], replace(regions()[1], region_id="COVER_REGION")))
    with pytest.raises(ContractError, match="Duplicate region role"):
        section(concrete_regions=(regions()[0], replace(regions()[1], role="cover")))
    with pytest.raises(ContractError, match="Duplicate reinforcement_id"):
        section(transverse_reinforcement=(ties(), replace(ties(), reinforcement_id="HOOP_01")))


def test_invalid_voids_and_unsupported_geometry_tag_are_rejected() -> None:
    with pytest.raises(ContractError, match="strictly inside"):
        RectangularRegionGeometry(gross(), (gross(),))
    with pytest.raises(ContractError, match="cannot overlap"):
        RectangularRegionGeometry(
            gross(),
            (RectangleGeometry(-100, 30, -100, 30), RectangleGeometry(0, 100, 0, 100)),
        )
    data = section().to_dict()
    data["geometry"]["geometry_type"] = "polygon"
    with pytest.raises(ContractError, match="Unsupported section geometry_type"):
        SectionDefinition.from_dict(data)


def test_invalid_transverse_size_spacing_orientation_or_legs_are_rejected() -> None:
    for changes in (
        {"diameter_mm": None, "area_mm2": None},
        {"area_mm2": 50},
        {"spacing_mm": 0},
        {"diameter_mm": -1},
        {"orientation": "y", "legs_z": 2},
        {"legs_y": 0},
        {"orientation": "unknown"},
    ):
        with pytest.raises(ContractError):
            ties(**changes)


def test_incompatible_units_and_axis_conventions_are_rejected() -> None:
    for units in (
        {"length": "cm", "area": "mm^2", "stress": "MPa", "force": "kN"},
        {"length": "mm", "area": "cm^2", "stress": "MPa", "force": "kN"},
        {"length": "mm", "area": "mm^2", "stress": "Pa", "force": "kN"},
    ):
        with pytest.raises(UnitBoundaryError, match="units must be"):
            section(units=units)
    with pytest.raises(ContractError, match="local y-z convention"):
        SectionCoordinateSystem(positive_z="down")
    data = section().to_dict()
    del data["coordinate_system"]["positive_y"]
    with pytest.raises(ContractError, match="missing required fields"):
        SectionDefinition.from_dict(data)
    data = section().to_dict()
    del data["units"]
    with pytest.raises(ContractError, match="missing required fields"):
        SectionDefinition.from_dict(data)


def test_stable_round_trip_and_rejection_of_unknown_fields_or_version() -> None:
    value = section(source="sap2000", external_name="COLUMN 400x600")
    restored = SectionDefinition.from_json(value.to_json())
    assert restored == value
    assert restored.to_json() == value.to_json()
    assert restored.to_dict()["coordinate_system"] == {
        "origin": "gross_geometry_centroid",
        "longitudinal_axis": "x",
        "view_direction": "from_positive_x_toward_origin",
        "positive_y": "right",
        "positive_z": "up",
    }
    assert "fiber" not in restored.to_json() and "patch" not in restored.to_json()
    data = value.to_dict()
    data["schema_version"] = "3"
    with pytest.raises(SchemaVersionError):
        SectionDefinition.from_dict(data)
    data = value.to_dict()
    data["opensees_patch"] = {}
    with pytest.raises(ContractError, match="Unknown fields"):
        SectionDefinition.from_dict(data)


def test_section_definition_uses_v2_artifact_hash_and_provenance_without_duplication() -> None:
    value = section()
    value.validate_material_references(materials())
    content = value.to_json().encode("utf-8")
    material_hashes = {
        material.material_id: hashlib.sha256(material.to_json().encode("utf-8")).hexdigest()
        for material in materials()
    }
    provenance = ProcessProvenance(
        schema_version="2",
        module_id="section_component_characterization",
        implementation_version="1B-test",
        resolved_configuration={"section_id": value.section_id},
        input_hashes=material_hashes,
        units=value.units,
    )
    artifact = ArtifactManifest(
        schema_version="2",
        artifact_id="COLUMN_400X600_definition",
        artifact_type="section_definition",
        module_id="section_component_characterization",
        stage_number="04",
        producer="test_section_definition_1b",
        uri="04_section_component_characterization/data/section_definition.json",
        sha256=hashlib.sha256(content).hexdigest(),
        units=value.units,
        provenance=provenance,
    )
    assert artifact.content_hash == hashlib.sha256(content).hexdigest()
    assert artifact.provenance.input_hashes == material_hashes
    assert ArtifactManifest.from_json(artifact.to_json()).provenance.signature == provenance.signature

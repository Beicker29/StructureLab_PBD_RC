"""Front 2 / 1C: neutral element identities and signed force states."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from structurelab_pbd_rc.contracts import (
    ArtifactManifest,
    ElementType,
    NormalizedStation,
    ProcessProvenance,
    SectionForceState,
    StructuralElementRef,
    validate_section_force_states,
)
from structurelab_pbd_rc.core.exceptions import ContractError, DependencyError, UnitBoundaryError


def element(**changes: object) -> StructuralElementRef:
    values: dict[str, object] = {
        "schema_version": "2",
        "element_id": "C23",
        "source": "structurelab",
        "element_type": "column",
    }
    values.update(changes)
    return StructuralElementRef(**values)


def state(**changes: object) -> SectionForceState:
    values: dict[str, object] = {
        "schema_version": "2",
        "element_id": "C23",
        "load_case": "DBE",
        "station": NormalizedStation(0.0),
        "P": 900.0,
        "Vy": -30.0,
        "Vz": 45.0,
        "T": -2.0,
        "My": 80.0,
        "Mz": -120.0,
    }
    values.update(changes)
    return SectionForceState(**values)


@pytest.mark.parametrize("kind", ["beam", "column", "wall"])
def test_element_types_do_not_require_a_section_assignment(kind: str) -> None:
    value = element(element_type=kind)
    assert value.element_type is ElementType(kind)
    assert "section_id" not in value.to_dict()


def test_external_name_is_distinct_from_internal_id_and_story_is_optional() -> None:
    imported = element(source="etabs", external_name="C23 : Story 04", story="Story 04",
                       external_section_name="ETABS_C40")
    assert imported.element_id == "C23"
    assert imported.external_name == "C23 : Story 04"
    assert imported.story == "Story 04"
    assert imported.external_section_name == "ETABS_C40"
    assert element().external_name is None
    assert element().story is None
    assert element().external_section_name is None


def test_section_id_cannot_be_deserialized_as_external_metadata() -> None:
    with pytest.raises(ContractError, match="Unknown fields"):
        StructuralElementRef.from_dict({**element().to_dict(), "section_id": "SEC_C23"})


@pytest.mark.parametrize("change", [
    {"element_id": ""}, {"element_type": "slab"},
    {"source": "ETABS"}, {"external_name": "   "}, {"story": "   "},
    {"external_section_name": "   "},
])
def test_invalid_element_identity_or_type_is_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ContractError):
        element(**change)


def test_force_state_contains_all_six_signed_resultants_with_declared_boundaries() -> None:
    value = state()
    assert (value.P, value.Vy, value.Vz, value.T, value.My, value.Mz) == (
        900.0, -30.0, 45.0, -2.0, 80.0, -120.0
    )
    assert value.units == {"force": "kN", "moment": "kN-m"}
    assert value.axes == {"P": "x", "Vy": "y", "Vz": "z", "T": "x", "My": "y", "Mz": "z"}
    assert value.sign_conventions["P"] == "compression_positive_tension_negative"
    assert value.sign_conventions["Vy"] == "positive_along_axis"
    assert value.sign_conventions["My"] == "positive_about_axis"
    assert value.action_face == "positive_x_cut_face"


def test_multiple_cases_combinations_and_stations_for_same_element() -> None:
    states = (
        state(),
        state(station=NormalizedStation(1.0)),
        state(load_case="MCE"),
        state(load_case=None, load_combination="1.2D+1.0L"),
        state(load_case="DBE", load_combination="Envelope", station=NormalizedStation(0.5)),
    )
    validate_section_force_states(states, elements=(element(),))
    assert [item.station.value for item in states] == [0.0, 1.0, 0.0, 0.0, 0.5]
    assert states[3].load_case is None
    assert states[4].load_combination == "Envelope"


def test_duplicate_state_keys_and_unresolved_elements_are_rejected() -> None:
    with pytest.raises(ContractError, match="Duplicate SectionForceState"):
        validate_section_force_states((state(), state(P=901)))
    with pytest.raises(ContractError, match="Duplicate SectionForceState"):
        validate_section_force_states((state(), state(load_case="dbe")))
    with pytest.raises(DependencyError, match="element_id"):
        validate_section_force_states((state(),), elements=(element(element_id="B1"),))
    with pytest.raises(ContractError, match="Duplicate element_id"):
        validate_section_force_states((state(),), elements=(element(), element(element_id="c23")))


@pytest.mark.parametrize("bad", [None, "", " ", "bad id"])
def test_force_state_rejects_invalid_element_id(bad: object) -> None:
    with pytest.raises(ContractError, match="element_id"):
        state(element_id=bad)


@pytest.mark.parametrize("station", [-0.1, 1.1, float("nan"), float("inf"), True, "0.5"])
def test_station_rejects_invalid_values(station: object) -> None:
    with pytest.raises(ContractError, match="station"):
        NormalizedStation(station)


def test_station_tag_prevents_silent_distance_or_plain_float_interpretation() -> None:
    with pytest.raises(ContractError, match="station.kind"):
        NormalizedStation(500, kind="distance_mm")
    with pytest.raises(ContractError, match="tagged NormalizedStation"):
        state(station=0.5)
    data = state().to_dict()
    data["station"] = {"kind": "distance_mm", "value": 500}
    with pytest.raises(ContractError, match="station.kind"):
        SectionForceState.from_dict(data)


@pytest.mark.parametrize("bad", [None, "4", float("nan"), float("inf"), True])
def test_non_numeric_or_nonfinite_force_is_rejected(bad: object) -> None:
    with pytest.raises(ContractError, match="P"):
        state(P=bad)


def test_load_identity_is_required_and_whitespace_ambiguity_rejected() -> None:
    with pytest.raises(ContractError, match="load_case and/or load_combination"):
        state(load_case=None, load_combination=None)
    with pytest.raises(ContractError, match="load_case"):
        state(load_case=" DBE ")


@pytest.mark.parametrize("change", [
    {"units": {"force": "N", "moment": "kN-m"}},
    {"units": {"force": "kN", "moment": "N-mm"}},
    {"axes": {"P": "x", "Vy": "z"}},
    {"sign_conventions": {"P": "tension_positive_compression_negative"}},
    {"action_face": "negative_x_cut_face"},
])
def test_external_units_axes_and_signs_are_rejected_without_conversion(change: dict[str, object]) -> None:
    with pytest.raises(UnitBoundaryError):
        state(**change)


def test_element_and_state_json_round_trip_is_stable_and_strict() -> None:
    ref = element(source="etabs", external_name="C23", story="L03",
                  external_section_name="ETABS_C40")
    value = state(station=NormalizedStation(0.25), load_case=None, load_combination="ULS")
    assert StructuralElementRef.from_json(ref.to_json()).to_json() == ref.to_json()
    assert SectionForceState.from_json(value.to_json()).to_json() == value.to_json()
    assert NormalizedStation.from_dict(value.station.to_dict()) == value.station
    with pytest.raises(ContractError, match="Unknown fields"):
        StructuralElementRef.from_dict({**ref.to_dict(), "nodes": [1, 2]})
    with pytest.raises(ContractError, match="Unknown fields"):
        SectionForceState.from_dict({**value.to_dict(), "V2": 1})
    with pytest.raises(ContractError, match="missing required fields"):
        SectionForceState.from_dict({key: item for key, item in value.to_dict().items() if key != "P"})


def test_provenance_and_artifact_hash_use_existing_v2_contracts() -> None:
    provenance = ProcessProvenance(
        schema_version="2",
        module_id="baseline_model",
        implementation_version="1c",
        resolved_configuration={"element_id": "C23", "external_section_name": "ETABS_C40"},
        input_hashes={"source_result": "a" * 64},
        units={"force": "kN", "moment": "kN-m"},
        sign_conventions={"P": "compression_positive_tension_negative"},
    )
    value = state(provenance=provenance)
    assert SectionForceState.from_json(value.to_json()).provenance.signature == provenance.signature
    digest = hashlib.sha256(value.to_json().encode("utf-8")).hexdigest()
    manifest = ArtifactManifest(
        schema_version="2",
        artifact_id="C23_DBE_I",
        artifact_type="section_force_state",
        module_id="baseline_model",
        stage_number="02",
        producer="1c_test",
        uri="02_baseline_model/C23_DBE_I.json",
        sha256=digest,
        units=value.units,
        sign_conventions=value.sign_conventions,
        axes=value.axes,
        provenance=provenance,
    )
    assert manifest.content_hash == digest
    assert ArtifactManifest.from_json(manifest.to_json()).provenance.signature == provenance.signature
    with pytest.raises(UnitBoundaryError, match="provenance.units"):
        state(provenance=replace(provenance, units={"force": "N"}))
    with pytest.raises(UnitBoundaryError, match="provenance.sign_conventions"):
        state(provenance=replace(provenance, sign_conventions={"P": "tension_positive"}))

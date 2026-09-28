"""Front 2 / 1A: physical material identity without scientific evaluation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from structurelab_pbd_rc.contracts import (
    ArtifactManifest,
    ConstitutiveReference,
    MaterialDefinition,
    MaterialType,
    ProcessProvenance,
)
from structurelab_pbd_rc.core.exceptions import (
    ContractError,
    SchemaVersionError,
    UnitBoundaryError,
)


def concrete(**changes: object) -> MaterialDefinition:
    fields: dict[str, object] = {
        "schema_version": "2",
        "material_id": "CONC_C28",
        "source": "structurelab",
        "material_type": MaterialType.CONCRETE,
        "nominal_strengths": {"fc": 28.0},
    }
    fields.update(changes)
    return MaterialDefinition(**fields)


def steel(**changes: object) -> MaterialDefinition:
    fields: dict[str, object] = {
        "schema_version": "2",
        "material_id": "REBAR_420",
        "source": "structurelab",
        "material_type": MaterialType.REINFORCING_STEEL,
        "nominal_strengths": {"fy": 420.0, "fu": 620.0},
    }
    fields.update(changes)
    return MaterialDefinition(**fields)


def scientific_result(
    model_id: str = "Mon_Mander1988", *, digest: str = "a" * 64
) -> ArtifactManifest:
    return ArtifactManifest(
        schema_version="2",
        artifact_id=f"{model_id}_scientific_result",
        artifact_type="material_scientific_result",
        module_id="material_characterization",
        stage_number="03",
        producer="structurelab_pbd_rc.workflow.stages.material_characterization",
        uri=f"03_material_characterization/set_01/{model_id}/data/scientific_result.json",
        sha256=digest,
        units={"stress": "MPa", "strain": "mm/mm"},
        sign_conventions={"stress": "compression_positive_tension_negative"},
        provenance=ProcessProvenance(
            schema_version="2",
            module_id="material_characterization",
            implementation_version="0.1.0",
            resolved_configuration={"model_id": model_id},
            input_hashes={"material_input": "b" * 64},
            units={"stress": "MPa"},
            sign_conventions={"stress": "compression_positive_tension_negative"},
        ),
    )


def reference(
    role: str, artifact: ArtifactManifest | None = None
) -> ConstitutiveReference:
    return ConstitutiveReference(
        role=role,
        model_id="Mon_Mander1988",
        project_id="tower_a",
        design_revision="rev_01",
        case_id="case_01",
        run_id="run_001",
        artifact=artifact if artifact is not None else scientific_result(),
    )


def test_structurelab_concrete_has_stable_identity_and_fc_in_mpa() -> None:
    material = concrete()
    assert material.material_id == "CONC_C28"
    assert material.source == "structurelab"
    assert material.material_type is MaterialType.CONCRETE
    assert material.nominal_strengths == {"fc": 28.0}
    assert material.units == {"length": "mm", "stress": "MPa", "force": "kN"}
    assert material.constitutive_references == ()


def test_structurelab_steel_stores_yield_and_optional_ultimate_strength() -> None:
    material = steel()
    assert material.nominal_strengths == {"fy": 420.0, "fu": 620.0}
    assert steel(nominal_strengths={"fy": 420}).nominal_strengths == {"fy": 420.0}


def test_external_name_is_preserved_but_not_the_internal_identity() -> None:
    material = concrete(source="etabs", external_name="C28 Imported / Floor 01")
    assert material.material_id == "CONC_C28"
    assert material.external_name == "C28 Imported / Floor 01"
    assert material.to_dict()["source"] == "etabs"
    assert concrete(source="sap2000", external_name="C28").material_id == material.material_id


def test_external_name_is_optional() -> None:
    assert concrete().external_name is None
    assert concrete().to_dict()["external_name"] is None
    with pytest.raises(ContractError, match="external_name"):
        concrete(external_name="  ")


def test_multiple_roles_reference_distinct_stage_03_results_without_curves() -> None:
    confined = reference("confined")
    unconfined = reference(
        "unconfined", scientific_result(digest="c" * 64)
    )
    unconfined = replace(
        unconfined,
        artifact=replace(unconfined.artifact, artifact_id="unconfined_scientific_result"),
    )
    material = concrete(constitutive_references=(confined, unconfined))
    assert [item.role for item in material.constitutive_references] == [
        "confined", "unconfined"
    ]
    assert [item.model_id for item in material.constitutive_references] == [
        "Mon_Mander1988", "Mon_Mander1988"
    ]
    assert "curve" not in material.to_dict()
    assert "curve" not in material.to_json()


@pytest.mark.parametrize("material_id", ["", " ", "A/B", "A B"])
def test_invalid_internal_ids_are_rejected(material_id: str) -> None:
    with pytest.raises(ContractError, match="material_id"):
        concrete(material_id=material_id)


@pytest.mark.parametrize("material_type", ["timber", "custom_concrete", ""])
def test_unknown_types_require_a_future_explicit_extension(material_type: str) -> None:
    with pytest.raises(ContractError, match="material_type"):
        concrete(material_type=material_type)


@pytest.mark.parametrize("value", [-1.0, 0.0, float("nan"), float("inf"), True, "28"])
def test_invalid_nominal_strengths_are_rejected(value: object) -> None:
    with pytest.raises(ContractError, match="fc"):
        concrete(nominal_strengths={"fc": value})


@pytest.mark.parametrize(
    "strengths",
    [{}, {"fy": 420.0}, {"fc": 28.0, "Ec": 26000.0}],
)
def test_concrete_requires_fc_and_does_not_accept_model_parameters(
    strengths: dict[str, float],
) -> None:
    with pytest.raises(ContractError, match="requires 'fc'"):
        concrete(nominal_strengths=strengths)


def test_steel_rejects_fu_below_fy_and_concrete_strength_field() -> None:
    with pytest.raises(ContractError, match="fu"):
        steel(nominal_strengths={"fy": 420.0, "fu": 400.0})
    with pytest.raises(ContractError, match="permits only"):
        steel(nominal_strengths={"fy": 420.0, "fc": 28.0})


def test_duplicate_roles_and_duplicate_artifacts_are_ambiguous() -> None:
    first = reference("confined")
    with pytest.raises(ContractError, match="Duplicate constitutive role"):
        concrete(constitutive_references=(first, reference("confined")))
    with pytest.raises(ContractError, match="Duplicate constitutive artifact"):
        concrete(constitutive_references=(first, reference("unconfined")))


def test_units_are_exact_internal_units_without_implicit_conversion() -> None:
    for units in (
        {"length": "cm", "stress": "MPa", "force": "kN"},
        {"length": "mm", "stress": "Pa", "force": "kN"},
        {"length": "mm", "stress": "MPa", "force": "N"},
        {"length": "mm", "stress": "MPa", "force": "kN", "time": "s"},
    ):
        with pytest.raises(UnitBoundaryError, match="exactly mm, MPa, and kN"):
            concrete(units=units)


def test_serialization_round_trip_is_stable_and_rejects_unknown_schema() -> None:
    material = concrete(
        source="etabs",
        external_name="C28 imported",
        constitutive_references=(reference("confined"),),
    )
    restored = MaterialDefinition.from_json(material.to_json())
    assert restored == material
    assert restored.to_json() == material.to_json()
    data = material.to_dict()
    data["schema_version"] = "3"
    with pytest.raises(SchemaVersionError):
        MaterialDefinition.from_dict(data)
    data = material.to_dict()
    data["parameters"] = {"mander": 1}
    with pytest.raises(ContractError, match="Unknown fields"):
        MaterialDefinition.from_dict(data)


def test_reference_reuses_v2_artifact_hash_and_process_provenance() -> None:
    item = reference("confined")
    material = concrete(constitutive_references=(item,))
    restored = MaterialDefinition.from_dict(material.to_dict())
    linked = restored.constitutive_references[0]
    assert linked.dependency.artifact_id == item.artifact.artifact_id
    assert linked.dependency.sha256 == item.artifact.sha256
    assert linked.artifact.provenance is not None
    assert linked.artifact.provenance.signature == item.artifact.provenance.signature
    assert linked.artifact.provenance.input_hashes == {"material_input": "b" * 64}
    assert linked.project_id == "tower_a" and linked.run_id == "run_001"


def test_reference_requires_stage_03_result_and_sufficient_identity() -> None:
    item = reference("confined")
    with pytest.raises(ContractError, match="Stage 03"):
        replace(item, artifact=replace(item.artifact, artifact_type="material_figure"))
    with pytest.raises(ContractError, match="provenance"):
        replace(item, artifact=replace(item.artifact, provenance=None))
    with pytest.raises(ContractError, match="run_id"):
        replace(item, run_id="")
    data = item.to_dict()
    data["artifact"] = None
    with pytest.raises(ContractError, match="constitutive artifact"):
        ConstitutiveReference.from_dict(data)
    data = item.to_dict()
    data["artifact"]["sha256"] = "bad"
    with pytest.raises(ContractError, match="SHA-256"):
        ConstitutiveReference.from_dict(data)


def test_nominal_strengths_are_copied_before_storage() -> None:
    strengths = {"fc": 28.0}
    material = concrete(nominal_strengths=strengths)
    strengths["fc"] = 35.0
    assert material.nominal_strengths == {"fc": 28.0}

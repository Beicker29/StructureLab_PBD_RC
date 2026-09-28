"""V2-013 units, signs, axes, and traceable conversion artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from structurelab_pbd_rc.contracts import (
    BoundaryArtifact,
    BoundaryDefinition,
    ConversionRecord,
    PhysicalQuantity,
    ReferenceSystem,
    SignConvention,
    STANDARD_GRAVITY_M_PER_S2,
    convert_boundary_artifact,
)
from structurelab_pbd_rc.core.exceptions import UnitBoundaryError


ROOT = Path(__file__).resolve().parents[2]


def boundary(
    quantity: PhysicalQuantity,
    unit: str,
    sign: SignConvention = SignConvention.NOT_APPLICABLE,
    reference: ReferenceSystem = ReferenceSystem.SCALAR,
    axis: str | None = None,
) -> BoundaryDefinition:
    return BoundaryDefinition(quantity, unit, sign, reference, axis)


def source_artifact(definition: BoundaryDefinition, *values: float) -> BoundaryArtifact:
    return BoundaryArtifact(
        schema_version="2",
        artifact_id="native_values",
        module_id="material_characterization",
        stage_number="03",
        boundary=definition,
        values=values,
    )


@pytest.mark.parametrize(
    ("quantity", "source_unit", "target_unit", "source_value", "expected"),
    [
        (PhysicalQuantity.LENGTH, "mm", "m", 1000.0, 1.0),
        (PhysicalQuantity.LENGTH, "m", "mm", 1.0, 1000.0),
        (PhysicalQuantity.FORCE, "N", "kN", 2500.0, 2.5),
        (PhysicalQuantity.FORCE, "kN", "N", 2.5, 2500.0),
        (PhysicalQuantity.CURVATURE, "1/mm", "1/m", 0.001, 1.0),
        (PhysicalQuantity.CURVATURE, "1/m", "1/mm", 1.0, 0.001),
        (
            PhysicalQuantity.ACCELERATION,
            "g",
            "m/s^2",
            1.0,
            STANDARD_GRAVITY_M_PER_S2,
        ),
        (
            PhysicalQuantity.ACCELERATION,
            "m/s^2",
            "g",
            STANDARD_GRAVITY_M_PER_S2,
            1.0,
        ),
    ],
)
def test_unit_conversions_create_new_traced_artifact(
    quantity: PhysicalQuantity,
    source_unit: str,
    target_unit: str,
    source_value: float,
    expected: float,
) -> None:
    source = source_artifact(boundary(quantity, source_unit), source_value)
    converted = convert_boundary_artifact(
        source,
        boundary(quantity, target_unit),
        artifact_id="converted_values",
        conversion_id="unit_conversion_01",
    )

    assert converted is not source
    assert converted.values == pytest.approx((expected,))
    assert source.values == (source_value,)
    assert converted.source_dependency is not None
    assert converted.source_dependency.artifact_id == source.artifact_id
    assert converted.source_dependency.sha256 == source.sha256
    assert converted.conversion is not None
    assert converted.conversion.source_unit == source_unit
    assert converted.conversion.target_unit == target_unit
    assert BoundaryArtifact.from_json(converted.to_json()) == converted


def test_mander_and_steel_sign_conventions_require_explicit_conversion() -> None:
    mander_native = boundary(
        PhysicalQuantity.STRESS,
        "MPa",
        SignConvention.COMPRESSION_POSITIVE_TENSION_NEGATIVE,
        ReferenceSystem.MATERIAL,
    )
    steel_style = boundary(
        PhysicalQuantity.STRESS,
        "MPa",
        SignConvention.TENSION_POSITIVE_COMPRESSION_NEGATIVE,
        ReferenceSystem.MATERIAL,
    )
    source = source_artifact(mander_native, 30.0, -3.0)
    converted = convert_boundary_artifact(
        source,
        steel_style,
        artifact_id="stress_tension_positive",
        conversion_id="explicit_sign_flip",
    )

    assert converted.values == (-30.0, 3.0)
    assert converted.conversion is not None
    assert converted.conversion.sign_factor == -1.0
    manifest = converted.to_manifest(
        uri="03_material_characterization/data/stress_tension_positive.json",
        producer="tests.v2_boundary",
    )
    assert manifest.sign_conventions["value"] == "tension_positive_compression_negative"
    assert manifest.dependencies[0].artifact_id == source.artifact_id
    assert manifest.metadata["conversion"]["conversion_id"] == "explicit_sign_flip"


def test_axis_and_dimension_mismatches_are_rejected() -> None:
    local_x = boundary(
        PhysicalQuantity.ACCELERATION,
        "g",
        SignConvention.POSITIVE_ALONG_AXIS,
        ReferenceSystem.STRUCTURE_GLOBAL,
        "+X",
    )
    local_y = boundary(
        PhysicalQuantity.ACCELERATION,
        "m/s^2",
        SignConvention.POSITIVE_ALONG_AXIS,
        ReferenceSystem.STRUCTURE_GLOBAL,
        "+Y",
    )
    source = source_artifact(local_x, 0.25)
    with pytest.raises(UnitBoundaryError, match="Coordinate-system or axis"):
        convert_boundary_artifact(
            source,
            local_y,
            artifact_id="wrong_axis",
            conversion_id="invalid_axis_change",
        )

    with pytest.raises(UnitBoundaryError, match="represents length"):
        boundary(PhysicalQuantity.FORCE, "mm")

    with pytest.raises(UnitBoundaryError, match="unit_factor must be"):
        ConversionRecord(
            conversion_id="tampered_factor",
            physical_quantity=PhysicalQuantity.LENGTH,
            source_unit="mm",
            target_unit="m",
            unit_factor=1.0,
            source_sign_convention=SignConvention.NOT_APPLICABLE,
            target_sign_convention=SignConvention.NOT_APPLICABLE,
            sign_factor=1.0,
            source_reference_system=ReferenceSystem.SCALAR,
            target_reference_system=ReferenceSystem.SCALAR,
            source_axis=None,
            target_axis=None,
            formula="invalid",
        )


def test_v1_material_fixture_is_read_only_and_not_silently_normalized() -> None:
    fixture = (
        ROOT
        / "tests/fixtures/v1/materials/stage_02/Modelos_constitutivos/COL75X75FC28MPa"
        / "confined_concrete/monotonic/Mon_Mander1988/data/curve.csv"
    )
    before = fixture.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()

    source = source_artifact(
        boundary(
            PhysicalQuantity.STRESS,
            "MPa",
            SignConvention.COMPRESSION_POSITIVE_TENSION_NEGATIVE,
            ReferenceSystem.MATERIAL,
        ),
        1.0,
    )
    convert_boundary_artifact(
        source,
        boundary(
            PhysicalQuantity.STRESS,
            "MPa",
            SignConvention.TENSION_POSITIVE_COMPRESSION_NEGATIVE,
            ReferenceSystem.MATERIAL,
        ),
        artifact_id="separate_v2_copy",
        conversion_id="v2_only",
    )

    assert fixture.read_bytes() == before
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == before_hash


"""V2-020 in-memory section service and frozen V1 regressions."""

from __future__ import annotations

import builtins
import csv
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest
import yaml

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.io.read_xlsx import list_xlsx_sheets, read_xlsx_rows
from structurelab_pbd_rc.services import (
    SectionCharacterizationInput,
    SectionCharacterizationResult,
    SectionCharacterizationService,
    SectionWorksheetInput,
    characterize_sections,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/stage_03/section_characterization.yaml"
FIXTURE_ROOT = ROOT / "tests/fixtures/v1/sections"
V1_OUTPUT_ROOT = ROOT / "outputs/stage_03"


def _config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _worksheets(config: Mapping[str, Any]) -> tuple[SectionWorksheetInput, ...]:
    workbook = ROOT / str(config["source"]["workbook"])
    return tuple(
        SectionWorksheetInput.from_rows(
            sheet_name,
            read_xlsx_rows(workbook, sheet_name=sheet_name),
        )
        for sheet_name in list_xlsx_sheets(workbook)
    )


def _request(
    config: Mapping[str, Any] | None = None,
    *,
    worksheets: Sequence[SectionWorksheetInput] | None = None,
) -> SectionCharacterizationInput:
    resolved = dict(config or _config())
    return SectionCharacterizationInput.from_resolved_inputs(
        resolved,
        worksheets=tuple(worksheets or _worksheets(resolved)),
        provenance={
            "configuration_sha256": "42dd8e6ae65cae24911224aeae11bbdae8a60f9f0a678458a2773142f2f337ab",
            "workbook_sha256": "ce38cc1aca600805cc852e46d7c564ba5646ed5fdcb4ba1bafdbcdddbd27f427",
            "fixture": "V2-006",
        },
    )


@pytest.fixture(scope="module")
def canonical_request() -> SectionCharacterizationInput:
    return _request()


@pytest.fixture(scope="module")
def canonical_result(
    canonical_request: SectionCharacterizationInput,
) -> SectionCharacterizationResult:
    return characterize_sections(canonical_request)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _assert_rows_equal_fixture(
    actual_rows: Sequence[Mapping[str, Any]], fixture_path: Path
) -> None:
    expected_rows = _csv_rows(fixture_path)
    assert len(actual_rows) == len(expected_rows), fixture_path
    for actual, expected in zip(actual_rows, expected_rows):
        assert set(actual) == set(expected), fixture_path
        for key, actual_value in actual.items():
            raw = expected[key]
            if isinstance(actual_value, bool):
                assert raw == str(actual_value), (fixture_path, key)
            elif isinstance(actual_value, int):
                assert int(raw) == actual_value, (fixture_path, key)
            elif isinstance(actual_value, float):
                assert float(raw) == actual_value, (fixture_path, key)
            else:
                assert raw == str(actual_value), (fixture_path, key)


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_all_ten_canonical_worksheets_match_every_frozen_v1_scientific_csv(
    canonical_result: SectionCharacterizationResult,
) -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert canonical_result.status == "completed"
    assert canonical_result.method == "asce_fema_energy_equivalent_m_phi"
    assert dict(canonical_result.units) == {"curvature": "1/m", "moment": "kN-m"}
    assert canonical_result.sheet_count == 10
    assert canonical_result.curve_count == 20
    assert [sheet.sheet_name for sheet in canonical_result.sheets] == manifest[
        "processed_sheet_order"
    ]

    for sheet, expected_sheet in zip(canonical_result.sheets, manifest["sheets"]):
        assert sheet.sheet_name == expected_sheet["sheet_name"]
        assert len(sheet.branches) == expected_sheet["curve_count"] == 2
        for mode_name, mode in (
            ("monotonica", sheet.monotonica),
            ("ciclica", sheet.ciclica),
        ):
            expected_mode = expected_sheet["modes"][mode_name]
            assert [dict(branch.curve) for branch in sheet.branches] == expected_mode["curves"]
            assert [dict(row) for row in mode.parameter_rows] == expected_mode["parameters"]
            assert list(mode.warnings) == expected_mode["warnings"]
            fixture_data = (
                FIXTURE_ROOT
                / "stage_03"
                / expected_sheet["output_folder"]
                / mode_name
                / "data"
            )
            _assert_rows_equal_fixture(
                mode.actual_curve_rows, fixture_data / "moment_curvature_curves.csv"
            )
            _assert_rows_equal_fixture(
                mode.bilinear_curve_rows, fixture_data / "bilinear_curves.csv"
            )
            _assert_rows_equal_fixture(
                mode.parameter_rows, fixture_data / "bilinearization_parameters.csv"
            )
            if mode_name == "ciclica":
                _assert_rows_equal_fixture(
                    mode.cut_point_rows, fixture_data / "cyclic_cut_points.csv"
                )


def test_explicit_auto_and_absent_cuts_preserve_legacy_behavior(
    canonical_request: SectionCharacterizationInput,
    canonical_result: SectionCharacterizationResult,
) -> None:
    first_sheet = canonical_result.sheets[0]
    positive, negative = first_sheet.branches

    assert positive.cut_selection.mode == "configured"
    assert dict(positive.cut_selection.point or {}) == {
        "phi": 0.085863,
        "moment": 753.754,
    }
    assert positive.ciclica_reuses_monotonic is False
    assert positive.ciclica["ultimate"] == {
        "phi": 0.085863,
        "moment": 753.754,
        "mode": "user_defined_phi_u",
    }

    assert negative.cut_selection.mode == "auto"
    assert negative.ciclica_reuses_monotonic is True
    assert negative.ciclica is negative.monotonic

    config = _config()
    config["cyclic_diagram"]["cut_points_by_sheet"].pop(first_sheet.sheet_name)
    absent = characterize_sections(
        _request(config, worksheets=(canonical_request.worksheets[0],))
    ).sheets[0]
    assert {branch.cut_selection.mode for branch in absent.branches} == {"absent"}
    assert all(branch.ciclica_reuses_monotonic for branch in absent.branches)
    # The structured reason is richer, while the V1-compatible table remains auto.
    assert {row["mode"] for row in absent.ciclica.cut_point_rows} == {"auto"}


def test_disabled_cyclic_configuration_reuses_monotonic_without_hysteretic_claim(
    canonical_request: SectionCharacterizationInput,
) -> None:
    config = _config()
    config["cyclic_diagram"]["enabled"] = False
    sheet = characterize_sections(
        _request(config, worksheets=(canonical_request.worksheets[0],))
    ).sheets[0]

    assert {branch.cut_selection.mode for branch in sheet.branches} == {"disabled"}
    assert all(branch.ciclica_reuses_monotonic for branch in sheet.branches)
    assert all(branch.ciclica is branch.monotonic for branch in sheet.branches)
    assert sheet.ciclica.diagram_type == "ciclica"
    assert sheet.ciclica.response_semantics == "truncated_or_reused_monotonic_backbone"
    assert sheet.ciclica.is_hysteretic is False
    assert all(branch.ciclica_is_hysteretic is False for branch in sheet.branches)


def test_best_effort_status_warning_areas_and_parameters_are_preserved(
    canonical_result: SectionCharacterizationResult,
) -> None:
    negative = canonical_result.sheets[0].branches[1]
    mechanics = negative.monotonic

    assert mechanics["status"] == "best_effort"
    assert mechanics["parameters"]["phi_u"] == 0.070961
    assert mechanics["parameters"]["Mu"] == 829.111
    assert mechanics["parameters"]["My"] == 899.415
    assert mechanics["parameters"]["Ke"] == 115432.64328839895
    assert mechanics["area"] == {
        "A_real": 58.5893857035,
        "A_bilinear": 58.098880136554136,
    }
    assert mechanics["parameters"]["absolute_relative_error"] == 0.008371918583139567
    assert canonical_result.warnings == (
        "V1 (2-3)T/negative_bending: bilinearization did not reach tolerance; "
        "best error = 0.008372.",
    )


def test_service_has_no_filesystem_side_effect_and_preserves_v1_outputs(
    canonical_request: SectionCharacterizationInput,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _tree_hashes(V1_OUTPUT_ROOT)

    def forbidden_open(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"scientific service attempted filesystem access: {args!r}")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    result = SectionCharacterizationService().evaluate(canonical_request)

    assert result.status == "completed"
    assert _tree_hashes(V1_OUTPUT_ROOT) == before


def test_provenance_is_returned_without_paths_or_io_resolution(
    canonical_request: SectionCharacterizationInput,
    canonical_result: SectionCharacterizationResult,
) -> None:
    provenance = canonical_result.provenance

    assert provenance["inputs"] is not canonical_request.provenance
    assert dict(provenance["inputs"]) == dict(canonical_request.provenance)
    assert provenance["scientific_kernel"] == "mechanics.sections.moment_curvature"
    assert provenance["idealization_kernel"] == "mechanics.idealization.energy_equivalent"
    assert provenance["implementation_version"] == "v2-020"


def test_service_rejects_non_native_units_at_the_v2_boundary() -> None:
    config = _config()
    worksheets = _worksheets(config)[:1]
    config["units"] = {"curvature": "1/mm", "moment": "N-mm"}

    with pytest.raises(ConfigError, match="native units"):
        _request(config, worksheets=worksheets)


def test_service_identity_remains_independent_from_the_workflow_handler(
    canonical_result: SectionCharacterizationResult,
) -> None:
    assert canonical_result.service_id == "section_characterization"
    assert canonical_result.implementation_version == "v2-020"




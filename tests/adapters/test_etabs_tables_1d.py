"""Small ETABS-shaped XLSX exports exercise the 1D boundary without ETABS itself."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from structurelab_pbd_rc.adapters.etabs import (
    ETABSImportError,
    ETABSImportResult,
    ETABSTablesAdapter,
)
from structurelab_pbd_rc.adapters.etabs.tables import REQUIRED_TABLES


SHEETS = {
    "Frame Assignments - Summary": "Frame Assigns - Summary",
    "Frame Assignments - Section Properties": "Frame Assigns - Sect Prop",
    "Frame Assignments - End Length Offsets": "Frame Assigns - End Len Offsets",
    "Frame Assignments - Output Stations": "Frame Assigns - Output Stations",
}


def source_tables() -> dict[str, dict[str, object]]:
    """Ten title/header/unit/data blocks modelled on the supplied ETABS export."""

    force_headers = [
        "Story", "Beam", "Unique Name", "Output Case", "Case Type", "Step Type",
        "Step Num", "Station", "P", "V2", "V3", "T", "M2", "M3",
        "Element", "Elem Station", "Location",
    ]
    force_units = ["", "", "", "", "", "", "", "mm", "kN", "kN", "kN",
                   "kN-m", "kN-m", "kN-m", "", "mm", ""]
    beam_rows = [
        ["L3", "B19", "31", "SPECX", "LinRespSpec", "Max", "", 200,
         -100, 30, -40, 2, 80, -120, "31", 200, ""],
        ["L3", "B19", "31", "SPECX", "LinRespSpec", "Max", "", 3800,
         -120, 35, -45, 3, 85, -125, "31", 3800, ""],
        ["L3", "B19", "31", "COMB1", "Combination", "Max", "", 200,
         -140, 38, -49, 4, 90, -130, "31", 200, ""],
        ["L3", "B19", "31", "COMB1", "Combination", "Min", "", 200,
         20, -10, 12, -1, -40, 50, "31", 200, ""],
    ]
    column_rows = [
        ["L3", "C1", "3", "DBE", "LinStatic", "", 1, 0,
         -900, 10, 20, 0, 110, 120, "3", 0, ""],
        ["L3", "C1", "3", "MCE", "LinStatic", "", 1, 3000,
         -1000, 11, 21, 0, 130, 140, "3", 3000, ""],
    ]
    return {
        "Program Control": {
            "headers": ["ProgramName", "Version", "CurrUnits"],
            "units": ["Text", "Text", "Text"],
            "rows": [["ETABS", "18.1.1", "kN, mm, C"]],
        },
        "Frame Assignments - Summary": {
            "headers": ["Story", "Label", "UniqueName", "Design Type", "Length",
                        "Analysis Section", "Design Section", "Max Station Spacing"],
            "units": ["", "", "", "", "mm", "", "", "mm"],
            "rows": [
                ["L3", "B19", "31", "Beam", 4000, "V40", "V40", 500],
                ["L3", "C1", "3", "Column", 3000, "C40", "C40", 500],
            ],
        },
        "Frame Assignments - Section Properties": {
            "headers": ["Story", "Label", "UniqueName", "Shape", "Section Property"],
            "units": ["", "", "", "", ""],
            "rows": [
                ["L3", "B19", "31", "Concrete Rectangular", "V40"],
                ["L3", "C1", "3", "Concrete Rectangular", "C40"],
            ],
        },
        "Frame Assignments - End Length Offsets": {
            "headers": ["Story", "Label", "UniqueName", "Offset Option", "Offset I",
                        "Offset J", "Rigid Factor"],
            "units": ["", "", "", "", "mm", "mm", ""],
            "rows": [
                ["L3", "B19", "31", "Auto", 200, 200, 0],
                ["L3", "C1", "3", "User", 0, 0, 0],
            ],
        },
        "Frame Assignments - Output Stations": {
            "headers": ["Story", "Label", "UniqueName", "Station Option", "Max Spacing",
                        "Min Stations"],
            "units": ["", "", "", "", "mm", ""],
            "rows": [
                ["L3", "B19", "31", "Max Spacing", 500, 3],
                ["L3", "C1", "3", "Min Stations", 500, 3],
            ],
        },
        "Beam Bays": {
            "headers": ["Label", "PointBayI", "PointBayJ", "GUID"],
            "units": ["", "", "", ""],
            "rows": [["B19", "14", "15", "beam-guid"]],
        },
        "Column Bays": {
            "headers": ["Label", "PointBayI", "PointBayJ", "IEndStory", "GUID"],
            "units": ["", "", "", "", ""],
            "rows": [["C1", "1", "1", "Below", "column-guid"]],
        },
        "Point Object Connectivity": {
            "headers": ["UniqueName", "Story", "PointBay", "X", "Y", "Z"],
            "units": ["", "", "", "mm", "mm", "mm"],
            "rows": [
                ["P14", "L3", "14", 0, 0, 3000],
                ["P15", "L3", "15", 4000, 0, 3000],
                ["P1", "L3", "1", 0, 0, 3000],
            ],
        },
        "Element Forces - Beams": {
            "headers": force_headers,
            "units": force_units,
            "rows": beam_rows,
        },
        "Element Forces - Columns": {
            "headers": ["Column" if item == "Beam" else item for item in force_headers],
            "units": force_units,
            "rows": column_rows,
        },
    }


def _cell(reference: str, value: object) -> str:
    if value is None or value == "":
        return f'<c r="{reference}" t="inlineStr"><is><t></t></is></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}"><v>{value}</v></c>'
    return f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def write_export(path: Path, tables: dict[str, dict[str, object]]) -> Path:
    """Write the same three-row ETABS title/header/units layout using OOXML only."""

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        sheet_entries: list[str] = []
        relationships: list[str] = []
        content_types: list[str] = []
        for index, (title, definition) in enumerate(tables.items(), start=1):
            sheet_name = SHEETS.get(title, title)
            headers = definition["headers"]
            units = definition["units"]
            rows = [[f"TABLE:  {title}"], headers, units, *definition["rows"]]
            xml_rows = []
            for row_number, row in enumerate(rows, start=1):
                cells = "".join(
                    _cell(f"{chr(65 + column)}{row_number}", value)
                    for column, value in enumerate(row)
                )
                xml_rows.append(f'<row r="{row_number}">{cells}</row>')
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>',
            )
            sheet_entries.append(
                f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
            )
            relationships.append(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(content_types) + '</Types>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(sheet_entries)}</sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(relationships) + '</Relationships>',
        )
    return path


def imported(tmp_path: Path, tables: dict[str, dict[str, object]] | None = None) -> ETABSImportResult:
    path = write_export(tmp_path / "etabs.xlsx", tables if tables is not None else source_tables())
    return ETABSTablesAdapter().import_xlsx(path)


def rejected(tmp_path: Path, tables: dict[str, dict[str, object]], code: str) -> ETABSImportError:
    with pytest.raises(ETABSImportError) as error:
        imported(tmp_path, tables)
    assert error.value.diagnostics[0].severity == "error"
    assert error.value.diagnostics[0].code == code
    return error.value


def test_ten_tables_identified_by_internal_title_despite_abbreviated_sheets(tmp_path: Path) -> None:
    result = imported(tmp_path)
    assert set(result.source_metadata["table_sheets"]) == set(REQUIRED_TABLES)
    assert result.source_metadata["table_sheets"]["Frame Assignments - Section Properties"] == (
        "Frame Assigns - Sect Prop"
    )
    assert len(result.elements) == 2


def test_beam_column_unique_name_label_story_and_external_section_metadata(tmp_path: Path) -> None:
    result = imported(tmp_path)
    beam, column = result.elements
    assert (beam.element_id, beam.external_name, beam.source, beam.element_type.value,
            beam.story, beam.external_section_name) == (
                "ETABS_FRAME_31", "31", "etabs", "beam", "L3", "V40"
            )
    assert (column.element_id, column.external_name, column.element_type.value,
            column.external_section_name) == ("ETABS_FRAME_3", "3", "column", "C40")
    assert all("section_id" not in element.to_dict() for element in result.elements)
    frames = result.source_metadata["frames"]
    assert [frame["label"] for frame in frames] == ["B19", "C1"]
    assert [frame["length_mm"] for frame in frames] == [4000, 3000]
    assert [frame["analysis_section"] for frame in frames] == ["V40", "C40"]


def test_explicit_internal_element_ids_do_not_replace_external_unique_names(tmp_path: Path) -> None:
    workbook = write_export(tmp_path / "etabs.xlsx", source_tables())
    result = ETABSTablesAdapter(
        element_ids_by_unique_name={"31": "B_23", "3": "C_01"},
    ).import_xlsx(workbook)
    assert result.elements[0].element_id == "B_23"
    assert result.elements[0].external_name == "31"
    assert result.force_states[0].element_id == "B_23"


def test_force_mapping_and_axial_tension_to_compression_sign(tmp_path: Path) -> None:
    result = imported(tmp_path)
    first = result.force_states[0]
    assert (first.P, first.Vy, first.Vz, first.T, first.My, first.Mz) == (
        100, 30, -40, 2, 80, -120
    )
    assert result.force_states[3].P == -20  # Positive ETABS P means tension.
    assert result.source_metadata["axial_sign_transform"].startswith("P_structurelab = -P_ETABS")


def test_normalized_stations_preserve_source_distances_lengths_and_offsets(tmp_path: Path) -> None:
    result = imported(tmp_path)
    assert [item.station.value for item in result.force_states] == [0.05, 0.95, 0.05, 0.05, 0, 1]
    details = result.force_states[0].provenance.resolved_configuration
    assert (details["station_etabs_mm"], details["length_mm"],
            details["offset_i_mm"], details["offset_j_mm"]) == (200, 4000, 200, 200)
    assert result.source_metadata["frames"][0]["station_option"] == "Max Spacing"
    assert result.source_metadata["frames"][0]["max_spacing_mm"] == 500


def test_cases_combinations_steps_and_spectrum_max_remain_uninterpreted(tmp_path: Path) -> None:
    result = imported(tmp_path)
    spectrum = result.force_states[0]
    assert (spectrum.load_case, spectrum.load_combination) == ("SPECX", None)
    assert (result.force_states[2].load_case, result.force_states[2].load_combination) == (
        None, "COMB1"
    )
    assert result.force_states[3].load_combination == "COMB1"  # Same station, Min step retained.
    metadata = spectrum.provenance.resolved_configuration
    assert (metadata["output_case"], metadata["case_type"], metadata["step_type"],
            metadata["step_num"]) == ("SPECX", "LinRespSpec", "Max", None)
    assert metadata["simultaneity_interpreted"] is False
    assert result.force_states[4].provenance.resolved_configuration["step_num"] == 1
    assert any(item.code == "non_simultaneous_spectrum_extrema" for item in result.warnings)


def test_connectivity_retains_bays_points_coordinates_and_end_story(tmp_path: Path) -> None:
    result = imported(tmp_path)
    assert len(result.connectivity["points"]) == 3
    assert result.connectivity["points"][1]["x_mm"] == 4000
    beam, column = result.connectivity["frame_bays"]
    assert (beam["element_id"], beam["point_i_unique_name"], beam["point_j_unique_name"]) == (
        "ETABS_FRAME_31", "P14", "P15"
    )
    assert (column["point_bay_i"], column["point_bay_j"], column["i_end_story"]) == (
        "1", "1", "Below"
    )
    assert column["point_i_unique_name"] is None
    assert column["point_j_unique_name"] == "P1"


def test_units_and_program_version_and_file_hash_are_auditable(tmp_path: Path) -> None:
    result = imported(tmp_path)
    path = tmp_path / "etabs.xlsx"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.source_metadata["software_version"] == "18.1.1"
    assert result.source_metadata["source_sha256"] == digest
    assert result.source_metadata["table_units"]["Element Forces - Beams"]["M3"] == "kN-m"
    provenance = result.force_states[0].provenance
    assert provenance.input_hashes == {"etabs_xlsx": digest}
    assert provenance.backend_version == "18.1.1"
    assert provenance.resolved_configuration["source_table"] == "Element Forces - Beams"
    assert provenance.resolved_configuration["unique_name"] == "31"
    assert provenance.resolved_configuration["raw_forces"]["P"] == -100


@pytest.mark.parametrize("table,column,wrong", [
    ("Frame Assignments - Summary", "Length", "cm"),
    ("Element Forces - Beams", "P", "kgf"),
    ("Element Forces - Columns", "M3", "kgf-cm"),
    ("Point Object Connectivity", "X", "cm"),
])
def test_nonstandard_units_require_reexport(tmp_path: Path, table: str, column: str,
                                             wrong: str) -> None:
    tables = source_tables()
    index = tables[table]["headers"].index(column)
    tables[table]["units"][index] = wrong
    error = rejected(tmp_path, tables, "invalid_units")
    assert "Reexport from ETABS" in str(error)
    assert wrong in str(error)


def test_program_currunits_disagreement_warns_when_table_units_are_valid(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Program Control"]["rows"][0][2] = "kip, in, F"
    result = imported(tmp_path, tables)
    assert any(item.code == "program_units_differ" for item in result.warnings)
    assert result.source_metadata["program_current_units"] == "kip, in, F"


def test_required_table_missing_is_error(tmp_path: Path) -> None:
    tables = source_tables()
    tables.pop("Frame Assignments - Output Stations")
    error = rejected(tmp_path, tables, "missing_table")
    assert "Frame Assignments - Output Stations" in str(error)


def test_duplicate_unique_name_is_error(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - Summary"]["rows"].append(
        deepcopy(tables["Frame Assignments - Summary"]["rows"][0])
    )
    rejected(tmp_path, tables, "duplicate_unique_name")


def test_unknown_frame_in_force_table_is_error(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Element Forces - Beams"]["rows"][0][2] = "999"
    rejected(tmp_path, tables, "unknown_frame")


def test_import_needs_no_structurelab_section_catalog_or_mapping(tmp_path: Path) -> None:
    result = imported(tmp_path)
    assert [element.external_section_name for element in result.elements] == ["V40", "C40"]
    assert all("section_id" not in element.to_dict() for element in result.elements)


def test_missing_analysis_section_is_optional_external_metadata(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - Summary"]["rows"][0][5] = ""
    result = imported(tmp_path, tables)
    assert result.elements[0].external_section_name is None
    assert any(item.code == "incomplete_external_section" for item in result.warnings)
    assert len(result.force_states) == 6


def test_missing_section_property_does_not_replace_analysis_section(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - Section Properties"]["rows"][0][4] = ""
    result = imported(tmp_path, tables)
    assert result.elements[0].external_section_name == "V40"
    assert any(item.code == "incomplete_external_section" for item in result.warnings)


def test_inconsistent_etabs_section_tables_still_rejected(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - Section Properties"]["rows"][0][4] = "OTHER"
    rejected(tmp_path, tables, "section_assignment_mismatch")


def test_design_type_and_force_table_mismatch_is_error(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - Summary"]["rows"][0][3] = "Column"
    rejected(tmp_path, tables, "element_type_mismatch")


@pytest.mark.parametrize("value", [0, -1, "", "4000"])
def test_missing_nonpositive_or_nonnumeric_length_is_error(tmp_path: Path, value: object) -> None:
    tables = source_tables()
    tables["Frame Assignments - Summary"]["rows"][0][4] = value
    error = rejected(tmp_path, tables, "missing_value" if value == "" else
                     "invalid_length" if isinstance(value, (int, float)) else "non_numeric")
    assert "Length" in str(error)


@pytest.mark.parametrize("station", [-1, 4001])
def test_station_outside_element_is_error(tmp_path: Path, station: float) -> None:
    tables = source_tables()
    tables["Element Forces - Beams"]["rows"][0][7] = station
    rejected(tmp_path, tables, "station_outside_element")


def test_small_station_roundoff_is_accepted_but_raw_value_is_preserved(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Element Forces - Beams"]["rows"][0][7] = -1e-7
    value = imported(tmp_path, tables).force_states[0]
    assert value.station.value == 0
    assert value.provenance.resolved_configuration["station_etabs_mm"] == -1e-7


@pytest.mark.parametrize("column", ["P", "V2", "V3", "T", "M2", "M3"])
def test_non_numeric_resultant_is_error(tmp_path: Path, column: str) -> None:
    tables = source_tables()
    index = tables["Element Forces - Beams"]["headers"].index(column)
    tables["Element Forces - Beams"]["rows"][0][index] = "bad"
    rejected(tmp_path, tables, "non_numeric")


def test_duplicate_force_row_is_error_but_max_min_both_import(tmp_path: Path) -> None:
    assert len(imported(tmp_path).force_states) == 6
    tables = source_tables()
    tables["Element Forces - Beams"]["rows"].append(
        deepcopy(tables["Element Forces - Beams"]["rows"][0])
    )
    rejected(tmp_path, tables, "duplicate_force_row")


def test_incomplete_offset_and_output_rows_warn_without_inventing_values(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - End Length Offsets"]["rows"].pop(0)
    tables["Frame Assignments - Output Stations"]["rows"].pop(0)
    result = imported(tmp_path, tables)
    assert {item.code for item in result.warnings} >= {"missing_offsets", "missing_output_stations"}
    assert result.source_metadata["frames"][0]["offset_i_mm"] is None


def test_station_spacing_disagreement_is_visible_without_changing_forces(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - Output Stations"]["rows"][0][4] = 600
    result = imported(tmp_path, tables)
    assert any(item.code == "station_spacing_mismatch" for item in result.warnings)
    assert result.force_states[0].station.value == 0.05


def test_duplicate_labels_are_not_assumed_to_identify_bay_element(tmp_path: Path) -> None:
    tables = source_tables()
    tables["Frame Assignments - Summary"]["rows"].append(
        ["L4", "B19", "32", "Beam", 4000, "V40", "V40", 500]
    )
    tables["Frame Assignments - Section Properties"]["rows"].append(
        ["L4", "B19", "32", "Concrete Rectangular", "V40"]
    )
    result = imported(tmp_path, tables)
    assert result.connectivity["frame_bays"][0]["element_id"] is None
    assert any(item.code == "unresolved_bay_label" for item in result.warnings)


def test_result_serialization_preserves_nested_v2_contracts_and_metadata(tmp_path: Path) -> None:
    result = imported(tmp_path)
    encoded = result.to_json()
    assert ETABSImportResult.from_json(encoded).to_json() == encoded
    assert ETABSImportResult.from_json(encoded).elements[0].external_section_name == "V40"
    assert result.force_states[0].provenance.signature == (
        ETABSImportResult.from_json(encoded).force_states[0].provenance.signature
    )

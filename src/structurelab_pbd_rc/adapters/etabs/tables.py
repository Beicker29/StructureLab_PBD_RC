"""Read the ten supported ETABS Excel Database Tables into neutral V2 identities."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from structurelab_pbd_rc.contracts._common import (
    copy_json_mapping,
    ensure_mapping,
    validate_identifier,
)
from structurelab_pbd_rc.contracts.elements import (
    NormalizedStation,
    SectionForceState,
    StructuralElementRef,
)
from structurelab_pbd_rc.contracts.provenance import ProcessProvenance
from structurelab_pbd_rc.core.exceptions import ConfigError, ContractError
from structurelab_pbd_rc.io.read_xlsx import list_xlsx_sheets, read_xlsx_rows


REQUIRED_TABLES = (
    "Program Control",
    "Frame Assignments - Summary",
    "Frame Assignments - Section Properties",
    "Frame Assignments - End Length Offsets",
    "Frame Assignments - Output Stations",
    "Beam Bays",
    "Column Bays",
    "Point Object Connectivity",
    "Element Forces - Beams",
    "Element Forces - Columns",
)

_EXPECTED_UNITS: dict[str, dict[str, str]] = {
    "Frame Assignments - Summary": {"Length": "mm", "Max Station Spacing": "mm"},
    "Frame Assignments - End Length Offsets": {"Offset I": "mm", "Offset J": "mm"},
    "Frame Assignments - Output Stations": {"Max Spacing": "mm"},
    "Point Object Connectivity": {"X": "mm", "Y": "mm", "Z": "mm"},
    "Element Forces - Beams": {
        "Station": "mm", "P": "kN", "V2": "kN", "V3": "kN",
        "T": "kN-m", "M2": "kN-m", "M3": "kN-m", "Elem Station": "mm",
    },
    "Element Forces - Columns": {
        "Station": "mm", "P": "kN", "V2": "kN", "V3": "kN",
        "T": "kN-m", "M2": "kN-m", "M3": "kN-m", "Elem Station": "mm",
    },
}
_REQUIRED_HEADERS: dict[str, tuple[str, ...]] = {
    "Program Control": ("ProgramName", "Version"),
    "Frame Assignments - Summary": (
        "Story", "Label", "UniqueName", "Design Type", "Length", "Analysis Section",
    ),
    "Frame Assignments - Section Properties": (
        "Story", "Label", "UniqueName", "Section Property",
    ),
    "Frame Assignments - End Length Offsets": ("UniqueName", "Offset I", "Offset J"),
    "Frame Assignments - Output Stations": ("UniqueName",),
    "Beam Bays": ("Label", "PointBayI", "PointBayJ"),
    "Column Bays": ("Label", "PointBayI", "PointBayJ"),
    "Point Object Connectivity": ("UniqueName", "Story", "PointBay", "X", "Y", "Z"),
    "Element Forces - Beams": (
        "Story", "Beam", "Unique Name", "Output Case", "Station",
        "P", "V2", "V3", "T", "M2", "M3",
    ),
    "Element Forces - Columns": (
        "Story", "Column", "Unique Name", "Output Case", "Station",
        "P", "V2", "V3", "T", "M2", "M3",
    ),
}
_TITLE_RE = re.compile(r"^\s*TABLE:\s*(.+?)\s*$", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_STATION_REL_TOL = 1e-9
_STATION_ABS_TOL_MM = 1e-6


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _text(value: object, *, name: str, table: str, row: int) -> str:
    if isinstance(value, bool) or value is None:
        raise ETABSImportError.single("missing_value", f"{name} is missing.", table, row)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    result = str(value)
    if not result.strip():
        raise ETABSImportError.single("missing_value", f"{name} is missing.", table, row)
    return result.strip()


def _optional_text(value: object) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _number(value: object, *, name: str, table: str, row: int) -> float:
    if value is None or value == "":
        raise ETABSImportError.single("missing_value", f"{name} is missing.", table, row)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ETABSImportError.single("non_numeric", f"{name} must be a numeric cell.", table, row)
    try:
        number = float(value)
    except OverflowError as exc:
        raise ETABSImportError.single("non_numeric", f"{name} must be finite.", table, row) from exc
    if not math.isfinite(number):
        raise ETABSImportError.single("non_numeric", f"{name} must be finite.", table, row)
    return number


@dataclass(frozen=True)
class ETABSDiagnostic:
    severity: Literal["error", "warning"]
    code: str
    message: str
    table: str | None = None
    row: int | None = None
    unique_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity, "code": self.code, "message": self.message,
            "table": self.table, "row": self.row, "unique_name": self.unique_name,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ETABSDiagnostic:
        return cls(**dict(ensure_mapping(value, name="ETABSDiagnostic")))


class ETABSImportError(ContractError):
    """A reliable neutral import cannot be constructed; diagnostics are retained."""

    def __init__(self, diagnostics: tuple[ETABSDiagnostic, ...]):
        self.diagnostics = diagnostics
        details = "; ".join(item.message for item in diagnostics if item.severity == "error")
        super().__init__(details or "ETABS import failed.")

    @classmethod
    def single(
        cls, code: str, message: str, table: str | None = None, row: int | None = None,
        unique_name: str | None = None,
    ) -> ETABSImportError:
        return cls((ETABSDiagnostic("error", code, message, table, row, unique_name),))


@dataclass(frozen=True)
class ETABSImportResult:
    """Neutral records plus source-only metadata; no demand selection or analysis."""

    elements: tuple[StructuralElementRef, ...]
    force_states: tuple[SectionForceState, ...]
    connectivity: dict[str, Any]
    source_metadata: dict[str, Any]
    diagnostics: tuple[ETABSDiagnostic, ...] = ()

    @property
    def warnings(self) -> tuple[ETABSDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "elements": [item.to_dict() for item in self.elements],
            "force_states": [item.to_dict() for item in self.force_states],
            "connectivity": copy_json_mapping(self.connectivity, name="connectivity"),
            "source_metadata": copy_json_mapping(self.source_metadata, name="source_metadata"),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ETABSImportResult:
        data = dict(ensure_mapping(value, name="ETABSImportResult"))
        expected = {"elements", "force_states", "connectivity", "source_metadata", "diagnostics"}
        if set(data) != expected:
            raise ContractError("ETABSImportResult has missing or unknown fields.")
        return cls(
            elements=tuple(StructuralElementRef.from_dict(item) for item in data["elements"]),
            force_states=tuple(SectionForceState.from_dict(item) for item in data["force_states"]),
            connectivity=copy_json_mapping(data["connectivity"], name="connectivity"),
            source_metadata=copy_json_mapping(data["source_metadata"], name="source_metadata"),
            diagnostics=tuple(ETABSDiagnostic.from_dict(item) for item in data["diagnostics"]),
        )

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> ETABSImportResult:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ContractError("ETABSImportResult JSON is invalid.") from exc
        return cls.from_dict(ensure_mapping(parsed, name="ETABSImportResult"))


@dataclass(frozen=True)
class _Row:
    number: int
    values: dict[str, Any]

    def get(self, column: str) -> Any:
        return self.values.get(_key(column))


@dataclass(frozen=True)
class _Table:
    title: str
    sheet: str
    headers: dict[str, str]
    units: dict[str, str | None]
    rows: tuple[_Row, ...]

    def unit(self, column: str) -> str | None:
        return self.units.get(_key(column))

    def has(self, column: str) -> bool:
        return _key(column) in self.headers


def _parse_table(sheet: str, raw_rows: list[dict[str, Any]]) -> _Table | None:
    title: str | None = None
    title_index = -1
    for index, row in enumerate(raw_rows[:8]):
        for key, value in row.items():
            if key.startswith("__") or not isinstance(value, str):
                continue
            match = _TITLE_RE.match(value)
            if match:
                title, title_index = match.group(1).strip(), index
                break
        if title is not None:
            break
    if title is None:
        if sheet not in REQUIRED_TABLES:
            return None
        title = sheet
    if title not in REQUIRED_TABLES:
        return None
    header_index = title_index + 1
    while header_index < len(raw_rows) and not any(
        value is not None and str(value).strip()
        for key, value in raw_rows[header_index].items() if not key.startswith("__")
    ):
        header_index += 1
    if header_index + 1 >= len(raw_rows):
        raise ETABSImportError.single("missing_header", f"{title} lacks headers or unit row.", title)
    header_row, unit_row = raw_rows[header_index:header_index + 2]
    columns: dict[str, str] = {}
    headers: dict[str, str] = {}
    for letter, value in header_row.items():
        if letter.startswith("__") or value is None or not str(value).strip():
            continue
        normalized = _key(str(value))
        if normalized in headers:
            raise ETABSImportError.single(
                "duplicate_header", f"Duplicate column {value!r} in {title}.", title,
                header_row["__row_number__"],
            )
        columns[letter] = normalized
        headers[normalized] = str(value).strip()
    units = {key: _optional_text(unit_row.get(letter)) for letter, key in columns.items()}
    rows = tuple(
        _Row(
            number=int(raw["__row_number__"]),
            values={normalized: raw.get(letter) for letter, normalized in columns.items()},
        )
        for raw in raw_rows[header_index + 2:]
        if any(raw.get(letter) is not None and str(raw.get(letter)).strip() for letter in columns)
    )
    return _Table(title, sheet, headers, units, rows)


def _read_tables(path: Path) -> dict[str, _Table]:
    try:
        sheet_names = list_xlsx_sheets(path)
        tables: dict[str, _Table] = {}
        for sheet in sheet_names:
            parsed = _parse_table(sheet, read_xlsx_rows(path, sheet_name=sheet))
            if parsed is None:
                continue
            if parsed.title in tables:
                raise ETABSImportError.single(
                    "duplicate_table", f"Duplicate ETABS table {parsed.title!r}.", parsed.title,
                )
            tables[parsed.title] = parsed
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, ETABSImportError):
            raise
        raise ETABSImportError.single("invalid_xlsx", f"Cannot read ETABS XLSX: {exc}") from exc
    missing = [name for name in REQUIRED_TABLES if name not in tables]
    if missing:
        raise ETABSImportError.single(
            "missing_table", f"Required ETABS tables are missing: {', '.join(missing)}."
        )
    for title, names in _REQUIRED_HEADERS.items():
        table = tables[title]
        absent = [name for name in names if not table.has(name)]
        if absent:
            raise ETABSImportError.single(
                "missing_column", f"{title} is missing columns: {', '.join(absent)}.", title,
            )
    return tables


def _verify_units(tables: Mapping[str, _Table]) -> None:
    mismatches: list[str] = []
    for title, expected in _EXPECTED_UNITS.items():
        table = tables[title]
        for column, unit in expected.items():
            if not table.has(column):
                continue  # Some optional display columns are omitted by ETABS.
            found = table.unit(column)
            if found != unit:
                mismatches.append(f"{title}.{column}: {found!r}, expected {unit!r}")
    if mismatches:
        raise ETABSImportError.single(
            "invalid_units",
            "ETABS table units are incompatible (" + "; ".join(mismatches) +
            "). Reexport from ETABS using length mm, force kN, and moment kN-m; "
            "this adapter does not convert units.",
        )


def _unique_rows(table: _Table) -> dict[str, _Row]:
    result: dict[str, _Row] = {}
    for row in table.rows:
        unique = _text(row.get("UniqueName"), name="UniqueName", table=table.title, row=row.number)
        key = unique.casefold()
        if key in result:
            raise ETABSImportError.single(
                "duplicate_unique_name", f"Duplicate UniqueName {unique!r} in {table.title}.",
                table.title, row.number, unique,
            )
        result[key] = row
    return result


def _frame_id(unique: str, explicit: Mapping[str, str] | None) -> str:
    if explicit is not None:
        value = explicit.get(unique.casefold())
        if value is None:
            raise ETABSImportError.single(
                "missing_element_mapping", f"No element_id mapping for ETABS UniqueName {unique!r}."
            )
        return validate_identifier(value, name="element_id")
    # The extra underscore distinguishes encoded names from every valid raw ID.
    token = unique if _IDENTIFIER_RE.fullmatch(unique) else "_" + unique.encode("utf-8").hex()
    return f"ETABS_FRAME_{token}"


def _mapping(values: Mapping[str, str], *, label: str) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise ContractError(f"{label} must be a mapping.")
    result: dict[str, str] = {}
    for source, target in values.items():
        if not isinstance(source, str) or not source.strip():
            raise ContractError(f"{label} has an empty source identifier.")
        key = source.casefold()
        if key in result:
            raise ContractError(f"{label} has ambiguous case-insensitive key {source!r}.")
        result[key] = validate_identifier(target, name=f"{label}[{source!r}]")
    return result


class ETABSTablesAdapter:
    """Import ten ETABS Database Tables from a unit-verified XLSX export."""

    def __init__(
        self,
        *,
        element_ids_by_unique_name: Mapping[str, str] | None = None,
    ) -> None:
        self.element_ids_by_unique_name = (
            _mapping(element_ids_by_unique_name, label="element_ids_by_unique_name")
            if element_ids_by_unique_name is not None else None
        )

    def import_xlsx(self, path: str | Path) -> ETABSImportResult:
        source = Path(path)
        if source.suffix.casefold() != ".xlsx" or not source.is_file():
            raise ETABSImportError.single("missing_xlsx", f"ETABS XLSX file not found: {source}.")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        tables = _read_tables(source)
        _verify_units(tables)  # Fail before IDs or results if the export is not in internal units.
        diagnostics: list[ETABSDiagnostic] = []
        program = tables["Program Control"]
        if len(program.rows) != 1:
            raise ETABSImportError.single("program_control", "Program Control must have one row.", program.title)
        program_row = program.rows[0]
        if _text(program_row.get("ProgramName"), name="ProgramName", table=program.title,
                 row=program_row.number).casefold() != "etabs":
            raise ETABSImportError.single("program_control", "Program Control is not ETABS.", program.title)
        version = _text(program_row.get("Version"), name="Version", table=program.title,
                        row=program_row.number)
        current_units = _optional_text(program_row.get("CurrUnits"))
        if current_units is not None and not ("kn" in current_units.casefold()
                                                  and "mm" in current_units.casefold()):
            diagnostics.append(ETABSDiagnostic(
                "warning", "program_units_differ",
                "Program Control CurrUnits differs from mm/kN; table column units were verified independently.",
                program.title, program_row.number,
            ))

        summary = tables["Frame Assignments - Summary"]
        properties = tables["Frame Assignments - Section Properties"]
        summaries = _unique_rows(summary)
        property_rows = _unique_rows(properties)
        offset_rows = _unique_rows(tables["Frame Assignments - End Length Offsets"])
        station_rows = _unique_rows(tables["Frame Assignments - Output Stations"])
        if set(summaries) != set(property_rows):
            raise ETABSImportError.single(
                "section_assignment_mismatch",
                "Summary and Section Properties have different UniqueName sets.", properties.title,
            )
        for title, rows in (("Frame Assignments - End Length Offsets", offset_rows),
                            ("Frame Assignments - Output Stations", station_rows)):
            unknown = set(rows) - set(summaries)
            if unknown:
                raise ETABSImportError.single(
                    "unknown_frame", f"{title} refers to unknown UniqueName values: {sorted(unknown)}.", title,
                )
        elements: list[StructuralElementRef] = []
        frame_context: dict[str, dict[str, Any]] = {}
        seen_element_ids: set[str] = set()
        for unique_key, row in summaries.items():
            unique = _text(row.get("UniqueName"), name="UniqueName", table=summary.title, row=row.number)
            label = _text(row.get("Label"), name="Label", table=summary.title, row=row.number)
            story = _text(row.get("Story"), name="Story", table=summary.title, row=row.number)
            design_type = _text(row.get("Design Type"), name="Design Type", table=summary.title,
                                row=row.number).casefold()
            if design_type not in {"beam", "column"}:
                raise ETABSImportError.single(
                    "invalid_design_type", f"Unsupported Design Type {design_type!r} for {unique!r}.",
                    summary.title, row.number, unique,
                )
            length = _number(row.get("Length"), name="Length", table=summary.title, row=row.number)
            if length <= 0:
                raise ETABSImportError.single(
                    "invalid_length", f"Frame {unique!r} requires positive Length.",
                    summary.title, row.number, unique,
                )
            section_name = _optional_text(row.get("Analysis Section"))
            property_row = property_rows[unique_key]
            property_section = _optional_text(property_row.get("Section Property"))
            if (section_name is not None and property_section is not None
                    and property_section.casefold() != section_name.casefold()):
                raise ETABSImportError.single(
                    "section_assignment_mismatch",
                    f"Frame {unique!r} has Summary section {section_name!r} but Section Properties "
                    f"has {property_section!r}.", properties.title, property_row.number, unique,
                )
            if section_name is None or property_section is None:
                diagnostics.append(ETABSDiagnostic(
                    "warning", "incomplete_external_section",
                    f"Frame {unique!r} has an incomplete external section assignment; "
                    "no StructureLab section is inferred.",
                    summary.title if section_name is None else properties.title,
                    row.number if section_name is None else property_row.number, unique,
                ))
            for field, expected in (("Label", label), ("Story", story)):
                found = _text(property_row.get(field), name=field, table=properties.title,
                              row=property_row.number)
                if found != expected:
                    raise ETABSImportError.single(
                        "frame_identity_mismatch", f"Frame {unique!r} has inconsistent {field}.",
                        properties.title, property_row.number, unique,
                    )
            element_id = _frame_id(unique, self.element_ids_by_unique_name)
            if element_id.casefold() in seen_element_ids:
                raise ETABSImportError.single(
                    "duplicate_element_id", f"Duplicate StructureLab element_id {element_id!r}.",
                    summary.title, row.number, unique,
                )
            seen_element_ids.add(element_id.casefold())
            offsets = offset_rows.get(unique_key)
            offset_i = offset_j = None
            if offsets is None:
                diagnostics.append(ETABSDiagnostic(
                    "warning", "missing_offsets", f"Frame {unique!r} has no End Length Offsets row.",
                    "Frame Assignments - End Length Offsets", unique_name=unique,
                ))
            else:
                for field, expected in (("Label", label), ("Story", story)):
                    if offsets.get(field) is not None and _text(
                        offsets.get(field), name=field,
                        table="Frame Assignments - End Length Offsets", row=offsets.number,
                    ) != expected:
                        raise ETABSImportError.single(
                            "frame_identity_mismatch", f"Frame {unique!r} has inconsistent {field} in offsets.",
                            "Frame Assignments - End Length Offsets", offsets.number, unique,
                        )
                offset_i = _number(offsets.get("Offset I"), name="Offset I",
                                   table="Frame Assignments - End Length Offsets", row=offsets.number)
                offset_j = _number(offsets.get("Offset J"), name="Offset J",
                                   table="Frame Assignments - End Length Offsets", row=offsets.number)
                if offset_i < 0 or offset_j < 0 or offset_i + offset_j >= length:
                    raise ETABSImportError.single(
                        "invalid_offsets", f"Frame {unique!r} has invalid I/J offsets for Length {length} mm.",
                        "Frame Assignments - End Length Offsets", offsets.number, unique,
                    )
            output_stations = station_rows.get(unique_key)
            if output_stations is None:
                diagnostics.append(ETABSDiagnostic(
                    "warning", "missing_output_stations",
                    f"Frame {unique!r} has no Output Stations row.",
                    "Frame Assignments - Output Stations", unique_name=unique,
                ))
            elif output_stations.get("Max Spacing") is not None:
                spacing = _number(output_stations.get("Max Spacing"), name="Max Spacing",
                                  table="Frame Assignments - Output Stations",
                                  row=output_stations.number)
                if spacing <= 0:
                    raise ETABSImportError.single(
                        "invalid_output_stations", f"Frame {unique!r} has nonpositive Max Spacing.",
                        "Frame Assignments - Output Stations", output_stations.number, unique,
                    )
                summary_spacing = row.get("Max Station Spacing")
                if summary_spacing is not None:
                    declared = _number(summary_spacing, name="Max Station Spacing",
                                       table=summary.title, row=row.number)
                    if not math.isclose(spacing, declared, rel_tol=1e-9, abs_tol=1e-6):
                        diagnostics.append(ETABSDiagnostic(
                            "warning", "station_spacing_mismatch",
                            f"Frame {unique!r} has Summary spacing {declared} mm but Output "
                            f"Stations spacing {spacing} mm.",
                            "Frame Assignments - Output Stations", output_stations.number, unique,
                        ))
            element = StructuralElementRef(
                schema_version="2", element_id=element_id, external_name=unique,
                source="etabs", element_type=design_type, story=story,
                external_section_name=section_name,
            )
            elements.append(element)
            frame_context[unique_key] = {
                "element_id": element_id, "unique_name": unique, "label": label,
                "story": story, "design_type": design_type,
                "analysis_section": section_name,
                "length_mm": length, "offset_i_mm": offset_i, "offset_j_mm": offset_j,
                "offset_option": _optional_text(offsets.get("Offset Option")) if offsets else None,
                "station_option": _optional_text(output_stations.get("Station Option"))
                if output_stations else None,
                "max_spacing_mm": output_stations.get("Max Spacing") if output_stations else None,
                "min_stations": output_stations.get("Min Stations") if output_stations else None,
            }

        connectivity = self._connectivity(tables, frame_context, diagnostics)
        states = self._forces(tables, frame_context, source, source_hash, version, diagnostics)
        source_metadata = {
            "source_file": str(source), "source_sha256": source_hash,
            "software": "ETABS", "software_version": version,
            "program_current_units": current_units,
            "table_sheets": {name: tables[name].sheet for name in REQUIRED_TABLES},
            "table_units": {
                name: {header: table.unit(header) for header in _EXPECTED_UNITS.get(name, {})
                       if table.has(header)}
                for name, table in tables.items()
            },
            "frames": list(frame_context.values()),
            "axial_sign_transform": "P_structurelab = -P_ETABS (ETABS analysis: tension positive)",
            "station_transform": "normalized = Station_mm / Length_mm",
        }
        return ETABSImportResult(
            tuple(elements), tuple(states), connectivity, source_metadata, tuple(diagnostics),
        )

    @staticmethod
    def _connectivity(
        tables: Mapping[str, _Table], frames: Mapping[str, dict[str, Any]],
        diagnostics: list[ETABSDiagnostic],
    ) -> dict[str, Any]:
        points_table = tables["Point Object Connectivity"]
        points: list[dict[str, Any]] = []
        point_ids: set[str] = set()
        by_bay: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in points_table.rows:
            unique = _text(row.get("UniqueName"), name="UniqueName",
                           table=points_table.title, row=row.number)
            if unique.casefold() in point_ids:
                raise ETABSImportError.single(
                    "duplicate_point", f"Duplicate point UniqueName {unique!r}.",
                    points_table.title, row.number, unique,
                )
            point_ids.add(unique.casefold())
            story = _text(row.get("Story"), name="Story", table=points_table.title, row=row.number)
            bay = _text(row.get("PointBay"), name="PointBay", table=points_table.title, row=row.number)
            point = {
                "unique_name": unique, "story": story, "point_bay": bay,
                "x_mm": _number(row.get("X"), name="X", table=points_table.title, row=row.number),
                "y_mm": _number(row.get("Y"), name="Y", table=points_table.title, row=row.number),
                "z_mm": _number(row.get("Z"), name="Z", table=points_table.title, row=row.number),
            }
            points.append(point)
            by_bay[(story.casefold(), bay.casefold())].append(point)
        by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for frame in frames.values():
            by_label[frame["label"].casefold()].append(frame)
        frame_bays: list[dict[str, Any]] = []
        for title, kind in (("Beam Bays", "beam"), ("Column Bays", "column")):
            table = tables[title]
            for row in table.rows:
                label = _text(row.get("Label"), name="Label", table=title, row=row.number)
                bay_i = _text(row.get("PointBayI"), name="PointBayI", table=title, row=row.number)
                bay_j = _text(row.get("PointBayJ"), name="PointBayJ", table=title, row=row.number)
                candidates = [frame for frame in by_label[label.casefold()]
                              if frame["design_type"] == kind]
                if len(candidates) != 1:
                    diagnostics.append(ETABSDiagnostic(
                        "warning", "unresolved_bay_label",
                        f"{title} Label {label!r} maps to {len(candidates)} {kind} frames; "
                        "Label is not a unique element ID.", title, row.number,
                    ))
                frame = candidates[0] if len(candidates) == 1 else None
                point_i = point_j = None
                i_end_story = _optional_text(row.get("IEndStory"))
                if frame is not None:
                    for bay, end in ((bay_i, "i"), (bay_j, "j")):
                        if end == "i" and i_end_story is not None and (
                            i_end_story.casefold() != frame["story"].casefold()
                        ):
                            # "Below" is not a story ID; do not link it to a same-story point.
                            continue
                        matches = by_bay.get((frame["story"].casefold(), bay.casefold()), [])
                        if len(matches) == 1:
                            if end == "i":
                                point_i = matches[0]["unique_name"]
                            else:
                                point_j = matches[0]["unique_name"]
                frame_bays.append({
                    "kind": kind, "label": label, "element_id": frame["element_id"] if frame else None,
                    "story": frame["story"] if frame else None,
                    "point_bay_i": bay_i, "point_bay_j": bay_j,
                    "i_end_story": i_end_story,
                    "point_i_unique_name": point_i, "point_j_unique_name": point_j,
                })
        return {"points": points, "frame_bays": frame_bays}

    @staticmethod
    def _forces(
        tables: Mapping[str, _Table], frames: Mapping[str, dict[str, Any]],
        source: Path, source_hash: str, version: str,
        diagnostics: list[ETABSDiagnostic],
    ) -> list[SectionForceState]:
        states: list[SectionForceState] = []
        seen: set[tuple[Any, ...]] = set()
        seen_frames: set[str] = set()
        non_simultaneous: set[tuple[str, str]] = set()
        for title, kind, label_column in (
            ("Element Forces - Beams", "beam", "Beam"),
            ("Element Forces - Columns", "column", "Column"),
        ):
            table = tables[title]
            for row in table.rows:
                unique = _text(row.get("Unique Name"), name="Unique Name", table=title,
                               row=row.number)
                frame = frames.get(unique.casefold())
                if frame is None:
                    raise ETABSImportError.single(
                        "unknown_frame", f"Force row refers to UniqueName {unique!r} absent from Summary.",
                        title, row.number, unique,
                    )
                seen_frames.add(unique.casefold())
                if frame["design_type"] != kind:
                    raise ETABSImportError.single(
                        "element_type_mismatch", f"Frame {unique!r} is {frame['design_type']} "
                        f"but appears in {title}.", title, row.number, unique,
                    )
                for field, expected in (("Story", frame["story"]),
                                        (label_column, frame["label"])):
                    found = _text(row.get(field), name=field, table=title, row=row.number)
                    if found != expected:
                        raise ETABSImportError.single(
                            "frame_identity_mismatch", f"Frame {unique!r} has inconsistent {field} "
                            f"in force results.", title, row.number, unique,
                        )
                output_case = _text(row.get("Output Case"), name="Output Case",
                                    table=title, row=row.number)
                case_type = _optional_text(row.get("Case Type"))
                step_type = _optional_text(row.get("Step Type"))
                step_num = row.get("Step Num")
                if step_num is not None and str(step_num).strip():
                    step_num = _number(step_num, name="Step Num", table=title, row=row.number)
                else:
                    step_num = None
                station_mm = _number(row.get("Station"), name="Station", table=title,
                                     row=row.number)
                length_mm = frame["length_mm"]
                tolerance = max(_STATION_ABS_TOL_MM, _STATION_REL_TOL * length_mm)
                if station_mm < -tolerance or station_mm > length_mm + tolerance:
                    raise ETABSImportError.single(
                        "station_outside_element",
                        f"Frame {unique!r} Station {station_mm} mm is outside [0, {length_mm}] mm.",
                        title, row.number, unique,
                    )
                normalized = min(1.0, max(0.0, station_mm / length_mm))
                values = {
                    name: _number(row.get(name), name=name, table=title, row=row.number)
                    for name in ("P", "V2", "V3", "T", "M2", "M3")
                }
                source_element = _optional_text(row.get("Element"))
                source_elem_station = row.get("Elem Station")
                if source_elem_station is not None and str(source_elem_station).strip():
                    source_elem_station = _number(source_elem_station, name="Elem Station",
                                                  table=title, row=row.number)
                else:
                    source_elem_station = None
                duplicate_key = (
                    unique.casefold(), output_case.casefold(), (case_type or "").casefold(),
                    (step_type or "").casefold(), step_num, station_mm, source_element,
                    source_elem_station,
                )
                if duplicate_key in seen:
                    raise ETABSImportError.single(
                        "duplicate_force_row", f"Duplicate force result for frame {unique!r}, "
                        f"case {output_case!r}, step {step_type!r}, station {station_mm} mm.",
                        title, row.number, unique,
                    )
                seen.add(duplicate_key)
                if (case_type or "").casefold() == "linrespspec" and (step_type or "").casefold() in {"max", "min"}:
                    non_simultaneous.add((output_case, step_type or ""))
                metadata = {
                    "source_file": str(source), "source_table": title, "source_sheet": table.sheet,
                    "source_row": row.number, "software": "ETABS", "software_version": version,
                    "unique_name": unique, "label": frame["label"], "story": frame["story"],
                    "output_case": output_case, "case_type": case_type,
                    "step_type": step_type, "step_num": step_num,
                    "station_etabs_mm": station_mm, "length_mm": length_mm,
                    "offset_i_mm": frame["offset_i_mm"], "offset_j_mm": frame["offset_j_mm"],
                    "element": source_element, "elem_station_mm": source_elem_station,
                    "raw_forces": values,
                    "axial_sign_transform": "P_structurelab = -P_ETABS",
                    "local_axes": "ETABS 1,2,3 -> StructureLab x,y,z",
                    "simultaneity_interpreted": False,
                }
                provenance = ProcessProvenance(
                    schema_version="2", module_id="baseline_model",
                    implementation_version="etabs_tables_adapter_1d",
                    resolved_configuration=metadata,
                    input_hashes={"etabs_xlsx": source_hash},
                    units={"force": "kN", "moment": "kN-m"},
                    sign_conventions={"P": "compression_positive_tension_negative"},
                    backend_version=version,
                )
                is_combination = (case_type or "").casefold() == "combination"
                states.append(SectionForceState(
                    schema_version="2", element_id=frame["element_id"],
                    load_case=None if is_combination else output_case,
                    load_combination=output_case if is_combination else None,
                    station=NormalizedStation(normalized),
                    P=-values["P"] if values["P"] else 0.0,
                    Vy=values["V2"], Vz=values["V3"], T=values["T"],
                    My=values["M2"], Mz=values["M3"], provenance=provenance,
                ))
        for output_case, step_type in sorted(non_simultaneous):
            diagnostics.append(ETABSDiagnostic(
                "warning", "non_simultaneous_spectrum_extrema",
                f"{output_case} / LinRespSpec / {step_type} was imported without treating "
                "component extrema as a simultaneous physical force state.",
            ))
        missing = sorted(set(frames) - seen_frames)
        if missing:
            diagnostics.append(ETABSDiagnostic(
                "warning", "frames_without_forces",
                f"No force rows were exported for UniqueName values: {missing}.",
            ))
        return states

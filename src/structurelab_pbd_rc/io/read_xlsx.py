"""Small XLSX readers based on the standard library."""

from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Any
from zipfile import ZipFile

from structurelab_pbd_rc.core.exceptions import ConfigError

_SHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_RELATIONSHIP_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_CELL_REFERENCE_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def _local_name(tag: str) -> str:
    """Return the XML local name without namespace."""

    return tag.rsplit("}", 1)[-1]


def _column_letters(cell_reference: str) -> str:
    """Return the column letters from a cell reference."""

    match = _CELL_REFERENCE_RE.match(cell_reference)
    if not match:
        raise ConfigError(f"Invalid XLSX cell reference: {cell_reference}")
    return match.group(1)


def _row_number(cell_reference: str) -> int:
    """Return the row number from a cell reference."""

    match = _CELL_REFERENCE_RE.match(cell_reference)
    if not match:
        raise ConfigError(f"Invalid XLSX cell reference: {cell_reference}")
    return int(match.group(2))


def _relationship_targets(archive: ZipFile) -> dict[str, str]:
    """Read workbook relationship targets by relationship id."""

    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets: dict[str, str] = {}
    for relationship in relationships.iter():
        if _local_name(relationship.tag) != "Relationship":
            continue
        relationship_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if relationship_id and target:
            targets[relationship_id] = target
    return targets


def _sheet_targets(archive: ZipFile) -> dict[str, str]:
    """Return sheet XML paths by visible sheet name."""

    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    targets = _relationship_targets(archive)
    sheets: dict[str, str] = {}
    for sheet in workbook.findall(".//a:sheet", _SHEET_NS):
        name = sheet.attrib.get("name")
        relationship_id = sheet.attrib.get(_RELATIONSHIP_ID)
        target = targets.get(str(relationship_id))
        if not name or not target:
            continue
        normalized = target.lstrip("/")
        if not normalized.startswith("xl/"):
            normalized = f"xl/{normalized}"
        sheets[name] = normalized
    return sheets


def list_xlsx_sheets(path: str | Path) -> list[str]:
    """Return visible sheet names in an XLSX workbook."""

    workbook_path = Path(path)
    if not workbook_path.exists():
        raise ConfigError(f"XLSX file not found: {workbook_path}")
    with ZipFile(workbook_path) as archive:
        return list(_sheet_targets(archive))


def _shared_strings(archive: ZipFile) -> list[str]:
    """Read shared strings when present."""

    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("a:si", _SHEET_NS):
        strings.append("".join(text.text or "" for text in item.findall(".//a:t", _SHEET_NS)))
    return strings


def _parse_number(value: str) -> Any:
    """Convert numeric cell text to int or float when possible."""

    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    """Return a Python value from an XLSX cell element."""

    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//a:t", _SHEET_NS))

    value_node = cell.find("a:v", _SHEET_NS)
    if value_node is None or value_node.text is None:
        return None

    raw_value = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw_value)]
    if cell_type == "b":
        return raw_value == "1"
    if cell_type == "str":
        return raw_value
    return _parse_number(raw_value)


def read_xlsx_rows(path: str | Path, *, sheet_name: str | None = None) -> list[dict[str, Any]]:
    """Read an XLSX sheet as row dictionaries keyed by Excel column letters."""

    workbook_path = Path(path)
    if not workbook_path.exists():
        raise ConfigError(f"XLSX file not found: {workbook_path}")

    with ZipFile(workbook_path) as archive:
        sheet_targets = _sheet_targets(archive)
        if not sheet_targets:
            raise ConfigError(f"XLSX workbook has no visible sheets: {workbook_path}")

        selected_sheet = sheet_name or next(iter(sheet_targets))
        if selected_sheet not in sheet_targets:
            available = ", ".join(sheet_targets)
            raise ConfigError(f"Sheet '{selected_sheet}' not found in {workbook_path}. Available sheets: {available}")

        shared_strings = _shared_strings(archive)
        root = ET.fromstring(archive.read(sheet_targets[selected_sheet]))
        rows: list[dict[str, Any]] = []
        for row in root.findall(".//a:sheetData/a:row", _SHEET_NS):
            row_number = int(row.attrib.get("r", "0"))
            parsed: dict[str, Any] = {"__row_number__": row_number}
            for cell in row.findall("a:c", _SHEET_NS):
                reference = cell.attrib.get("r")
                if not reference:
                    continue
                parsed["__row_number__"] = _row_number(reference)
                parsed[_column_letters(reference)] = _cell_value(cell, shared_strings)
            rows.append(parsed)
        return rows


def read_xlsx_table(path: str | Path, *, sheet_name: str | None = None) -> list[list[Any]]:
    """Read an XLSX sheet as a rectangular table."""

    rows = read_xlsx_rows(path, sheet_name=sheet_name)
    columns = sorted(
        {key for row in rows for key in row if not key.startswith("__")},
        key=lambda column: sum((ord(char) - 64) * 26**index for index, char in enumerate(reversed(column))),
    )
    return [[row.get(column) for column in columns] for row in rows]

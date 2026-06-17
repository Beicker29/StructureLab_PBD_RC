"""Minimal XLSX export helpers using the standard library."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def _cell_reference(row_index: int, column_index: int) -> str:
    letters = ""
    index = column_index
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index}"


def _sheet_xml(rows: list[dict[str, Any]]) -> str:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    all_rows = [dict(zip(headers, headers))] + rows if headers else []
    xml_rows: list[str] = []
    for row_number, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        for col_number, header in enumerate(headers, start=1):
            value = row.get(header, "")
            ref = _cell_reference(row_number, col_number)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        xml_rows.append(f"<row r=\"{row_number}\">{''.join(cells)}</row>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
        "</worksheet>"
    )


def write_xlsx(rows: list[dict[str, Any]], path: str | Path, *, sheet_name: str = "Sheet1") -> Path:
    """Write a single-sheet XLSX file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return output_path


def export_tables_to_excel(tables: dict[str, list[dict[str, Any]]], output_dir: str | Path) -> dict[str, Path]:
    """Export named tables to individual XLSX files."""

    output = Path(output_dir)
    paths: dict[str, Path] = {}
    for name, rows in tables.items():
        paths[name] = write_xlsx(rows, output / f"{name}.xlsx", sheet_name=name[:31])
    return paths

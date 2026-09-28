"""Deterministic in-memory serializers for V2 tabular artifacts."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def _headers(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    return headers


def csv_rows_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    headers = _headers(rows)
    writer = csv.DictWriter(stream, fieldnames=headers)
    writer.writeheader()
    writer.writerows({key: row.get(key, "") for key in headers} for row in rows)
    return stream.getvalue().encode("utf-8")


def etabs_spectrum_bytes(
    rows: Sequence[Mapping[str, Any]],
    *,
    period_key: str,
    value_key: str,
) -> bytes:
    return "".join(
        f"{float(row[period_key]):.8f}\t{float(row[value_key]):.8f}\n"
        for row in rows
    ).encode("ascii")


def _cell_reference(row_index: int, column_index: int) -> str:
    letters = ""
    index = column_index
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index}"


def _sheet_xml(rows: Sequence[Mapping[str, Any]]) -> str:
    headers = _headers(rows)
    all_rows: list[Mapping[str, Any]] = [dict(zip(headers, headers)), *rows] if headers else []
    xml_rows: list[str] = []
    for row_number, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        for column_number, header in enumerate(headers, start=1):
            value = row.get(header, "")
            reference = _cell_reference(row_number, column_number)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{reference}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{reference}" t="inlineStr"><is><t>'
                    f"{escape(str(value))}</t></is></c>"
                )
        xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


def _write_zip_text(archive: ZipFile, name: str, value: str) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, value.encode("utf-8"))


def xlsx_rows_bytes(
    rows: Sequence[Mapping[str, Any]],
    *,
    sheet_name: str,
) -> bytes:
    """Create a deterministic single-sheet XLSX without touching filesystem."""

    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        _write_zip_text(
            archive,
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        _write_zip_text(
            archive,
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        _write_zip_text(
            archive,
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
        _write_zip_text(
            archive,
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        _write_zip_text(archive, "xl/worksheets/sheet1.xml", _sheet_xml(rows))
    return stream.getvalue()

"""Minimal PDF export helper."""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap


def _escape_pdf_text(text: str) -> str:
    """Escape text for a PDF string literal."""

    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_lines(lines: list[str], width: int = 92) -> list[str]:
    """Wrap long lines while preserving blank lines."""

    wrapped: list[str] = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(wrap(line, width=width, replace_whitespace=False) or [""])
    return wrapped


def _page_stream(lines: list[str]) -> bytes:
    """Return a PDF text stream for one page."""

    safe_lines = [_escape_pdf_text(line) for line in lines]
    text_commands = ["BT", "/F1 11 Tf", "50 780 Td"]
    for index, line in enumerate(safe_lines):
        if index:
            text_commands.append("0 -16 Td")
        text_commands.append(f"({line}) Tj")
    text_commands.append("ET")
    return "\n".join(text_commands).encode("latin-1", errors="replace")


def export_report_to_pdf(lines: list[str], path: str | Path) -> Path:
    """Write a text PDF report with automatic wrapping and pagination."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wrapped_lines = _wrap_lines(lines)
    lines_per_page = 45
    pages = [wrapped_lines[index : index + lines_per_page] for index in range(0, len(wrapped_lines), lines_per_page)]
    if not pages:
        pages = [[""]]

    font_object_number = 3
    page_objects: list[bytes] = []
    content_objects: list[bytes] = []
    page_numbers: list[int] = []
    next_object_number = 4
    for page_lines in pages:
        page_number = next_object_number
        content_number = next_object_number + 1
        next_object_number += 2
        page_numbers.append(page_number)
        page_objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
                f"/Contents {content_number} 0 R >>"
            ).encode("ascii")
        )
        stream = _page_stream(page_lines)
        content_objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_numbers)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_object, content_object in zip(page_objects, content_objects):
        objects.append(page_object)
        objects.append(content_object)

    content = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    output_path.write_bytes(bytes(content))
    return output_path

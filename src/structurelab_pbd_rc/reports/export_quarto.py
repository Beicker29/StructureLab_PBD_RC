"""Quarto report export helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def find_quarto_command() -> Path:
    """Return the Quarto command installed as an external system tool."""

    discovered = shutil.which("quarto")
    if discovered:
        return Path(discovered)

    user_profile = Path.home()
    candidates = (
        user_profile / "AppData" / "Local" / "Programs" / "Quarto" / "bin" / "quarto.exe",
        user_profile / "AppData" / "Local" / "Programs" / "Quarto" / "bin" / "quarto.cmd",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Quarto was not found as an external system tool.")


def write_quarto_source(content: str, path: str | Path) -> Path:
    """Write a Quarto source document."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def render_quarto_pdf(qmd_path: str | Path) -> Path:
    """Render a Quarto document to PDF through Typst and return the PDF path."""

    source_path = Path(qmd_path)
    quarto = find_quarto_command()
    command = [str(quarto), "render", source_path.name, "--to", "typst"]
    completed = subprocess.run(
        command,
        cwd=source_path.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Quarto render failed for {source_path}: {message}")
    pdf_path = source_path.with_suffix(".pdf")
    if not pdf_path.exists():
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Quarto render did not create {pdf_path}: {message}")
    intermediate_typ = source_path.with_suffix(".typ")
    if intermediate_typ.exists():
        intermediate_typ.unlink()
    intermediate_files = source_path.parent / f"{source_path.stem}_files"
    if intermediate_files.exists():
        shutil.rmtree(intermediate_files)
    return pdf_path

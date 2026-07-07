"""XLSX reader tests."""

from __future__ import annotations

from pathlib import Path

from structurelab_pbd_rc.io.read_xlsx import list_xlsx_sheets, read_xlsx_rows, read_xlsx_table
from structurelab_pbd_rc.reports.export_excel import write_xlsx


def test_read_xlsx_rows_from_minimal_workbook(tmp_path: Path) -> None:
    workbook_path = tmp_path / "moment_curvature.xlsx"
    write_xlsx(
        [
            {"phi_pos": 0.0, "M_pos": 0.0, "phi_neg": 0.0, "M_neg": 0.0},
            {"phi_pos": 0.001, "M_pos": 100.0, "phi_neg": -0.001, "M_neg": -95.0},
        ],
        workbook_path,
        sheet_name="Curva",
    )

    assert list_xlsx_sheets(workbook_path) == ["Curva"]
    rows = read_xlsx_rows(workbook_path, sheet_name="Curva")
    table = read_xlsx_table(workbook_path, sheet_name="Curva")

    assert rows[0]["A"] == "phi_pos"
    assert rows[1]["A"] == 0
    assert rows[2]["B"] == 100
    assert table[0] == ["phi_pos", "M_pos", "phi_neg", "M_neg"]

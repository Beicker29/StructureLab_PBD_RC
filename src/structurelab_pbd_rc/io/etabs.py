"""ETABS text-file exporters."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def write_etabs_response_spectrum_txt(
    rows: list[dict[str, Any]],
    path: str | Path,
    *,
    period_key: str,
    value_key: str,
) -> Path:
    """Write an ETABS From File response-spectrum text file.

    ETABS reads one period-value pair per line when the function is defined as
    Period vs Value. The file intentionally has no header, so ETABS can import
    it with Header Lines to Skip = 0.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="ascii", newline="\n") as file:
        for row in rows:
            period = float(row[period_key])
            value = float(row[value_key])
            file.write(f"{period:.8f}\t{value:.8f}\n")
    return output_path

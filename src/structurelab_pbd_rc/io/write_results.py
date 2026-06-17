"""Result writers."""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Any

from structurelab_pbd_rc.io.serialization import to_json_safe


def write_json_result(data: dict[str, Any], path: str | Path) -> Path:
    """Write a JSON result file and return its path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(to_json_safe(data), file, indent=2, ensure_ascii=True)
    return output_path


def write_csv_rows(rows: list[dict[str, Any]], path: str | Path) -> Path:
    """Write dictionaries to CSV and return the output path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: to_json_safe(row.get(key, "")) for key in fieldnames})
    return output_path

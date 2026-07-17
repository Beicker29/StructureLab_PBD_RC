"""Shared helpers for stage design flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structurelab_pbd_rc.io.paths import ensure_stage_output_dirs
from structurelab_pbd_rc.io.read_config import load_stage_config
from structurelab_pbd_rc.io.write_results import write_csv_rows
from structurelab_pbd_rc.reports.export_excel import write_xlsx


def prepare_stage_from_config(
    config_path: str | Path,
    output_root: str | Path = "outputs",
    *,
    required_keys: tuple[str, ...] = (),
    output_subdirectories: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Load a stage config and prepare its output directories."""

    config = load_stage_config(config_path, required_keys=required_keys)
    stage_id = str(config.get("stage_id", Path(config_path).stem))
    if output_subdirectories is None:
        output_dirs = ensure_stage_output_dirs(stage_id, output_root=output_root)
    else:
        output_dirs = ensure_stage_output_dirs(stage_id, output_root=output_root, subdirectories=output_subdirectories)
    return {
        "stage_id": stage_id,
        "config": config,
        "output_dirs": output_dirs,
        "status": "prepared",
    }


def write_stage_table_pair(
    rows: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    filename_stem: str,
    sheet_name: str,
    key_prefix: str,
) -> dict[str, Path]:
    """Write one stage table as CSV and XLSX with consistent artifact keys."""

    directory = Path(output_dir)
    return {
        f"{key_prefix}_csv": write_csv_rows(rows, directory / f"{filename_stem}.csv"),
        f"{key_prefix}_xlsx": write_xlsx(rows, directory / f"{filename_stem}.xlsx", sheet_name=sheet_name),
    }

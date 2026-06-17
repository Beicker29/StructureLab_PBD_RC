"""Taller 1 workflow tests."""

from __future__ import annotations

import json
from pathlib import Path

from structurelab_pbd_rc.workflows.workshop_01_material_characterization import run


def test_workshop_01_prepares_output_directories(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/workshops/workshop_01_material_characterization.yaml"),
        output_root=tmp_path,
    )

    assert result["status"] == "prepared"
    assert result["workshop_id"] == "workshop_01"
    for name in ("root", "figures", "tables", "reports", "data"):
        assert result["output_dirs"][name].exists()


def test_workshop_01_writes_initial_results_json(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/workshops/workshop_01_material_characterization.yaml"),
        output_root=tmp_path,
    )

    results_path = result["results_path"]
    assert results_path.exists()
    assert results_path == tmp_path / "workshop_01" / "data" / "workshop_01_results.json"

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    assert payload["workshop_id"] == "workshop_01"
    assert payload["status"] == "completed"
    assert payload["computed_results"]["concrete_curves"]
    assert payload["metrics"]


def test_workshop_01_creates_expected_artifacts(tmp_path: Path) -> None:
    result = run(
        config_path=Path("configs/workshops/workshop_01_material_characterization.yaml"),
        output_root=tmp_path,
    )

    expected = [
        "data_concrete_curves",
        "data_steel_curves",
        "data_mesh_curves",
        "table_curve_metrics",
        "figure_concrete",
        "figure_steel_buckling",
        "figure_mesh",
        "figure_core_sketch",
        "report_pdf",
    ]
    for key in expected:
        assert Path(result["generated_files"][key]).exists()

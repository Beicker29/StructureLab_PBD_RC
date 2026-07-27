"""Path helpers for project data and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from structurelab_pbd_rc.core.constants import DEFAULT_STAGE_OUTPUT_SUBDIRECTORIES


@dataclass(frozen=True)
class ProjectPaths:
    """Common project paths."""

    root: Path

    @classmethod
    def from_cwd(cls) -> "ProjectPaths":
        """Build paths using the current working directory as project root."""

        return cls(root=Path.cwd())

    @property
    def configs(self) -> Path:
        """Return the configs directory."""

        return self.root / "configs"

    @property
    def outputs(self) -> Path:
        """Return the outputs directory."""

        return self.root / "outputs"

    @property
    def src(self) -> Path:
        """Return the src directory."""

        return self.root / "src"


def ensure_stage_output_dirs(
    stage_id: str,
    output_root: str | Path = "outputs",
    subdirectories: tuple[str, ...] = DEFAULT_STAGE_OUTPUT_SUBDIRECTORIES,
) -> dict[str, Path]:
    """Create and return the standard output directories for a stage."""

    root = Path(output_root) / stage_id
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {"root": root}
    for subdirectory in subdirectories:
        path = root / subdirectory
        path.mkdir(parents=True, exist_ok=True)
        paths[subdirectory] = path
    return paths


def ensure_material_model_output_dirs(
    *,
    stage_id: str,
    material: str,
    analysis_type: str,
    model: str,
    output_root: str | Path = "outputs",
) -> dict[str, Path]:
    """Create model-owned data, figures and reports directories."""

    root = Path(output_root) / stage_id / material / analysis_type / model
    paths = {
        "root": root,
        "data": root / "data",
        "figures": root / "figures",
        "reports": root / "reports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def stage_results_json_path(output_dirs: dict[str, Path], filename: str = "stage_results.json") -> Path:
    """Return the JSON results path inside a prepared stage data directory."""

    data_dir = output_dirs.get("data")
    if data_dir is None:
        data_dir = output_dirs["root"] / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / filename

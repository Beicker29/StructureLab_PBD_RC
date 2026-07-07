"""Command-line runner for StructureLab_PBD_RC stages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow "python -m structurelab_pbd_rc.cli.run ..." without external PYTHONPATH setup.
SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structurelab_pbd_rc.design.stages.stage_01_material_characterization import (
    DEFAULT_CONFIG_PATH as STAGE_01_DEFAULT_CONFIG_PATH,
)
from structurelab_pbd_rc.design.stages.stage_01_material_characterization import run as run_stage_01
from structurelab_pbd_rc.design.stages.stage_02_section_characterization import (
    DEFAULT_CONFIG_PATH as STAGE_02_DEFAULT_CONFIG_PATH,
)
from structurelab_pbd_rc.design.stages.stage_02_section_characterization import run as run_stage_02

STAGES = {
    "stage_01": {
        "default_config": STAGE_01_DEFAULT_CONFIG_PATH,
        "runner": run_stage_01,
    },
    "stage_02": {
        "default_config": STAGE_02_DEFAULT_CONFIG_PATH,
        "runner": run_stage_02,
    },
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m structurelab_pbd_rc.cli.run",
        description="Run a StructureLab_PBD_RC stage.",
    )
    parser.add_argument(
        "stage",
        nargs="?",
        default="stage_01",
        choices=sorted(STAGES),
        help="Stage id to run. Defaults to stage_01.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the stage YAML config.",
    )
    parser.add_argument(
        "--output-root",
        default="outputs",
        help="Directory where stage outputs are created.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a stage from the command line."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    stage = STAGES[args.stage]
    config_path = args.config or str(stage["default_config"])
    result = stage["runner"](config_path=config_path, output_root=args.output_root)
    print(f"Prepared {result['stage_id']} outputs:")
    print(f"  title: {result['config']['title']}")
    print(f"  config: {config_path}")
    for name, path in result["output_dirs"].items():
        print(f"  {name}: {path}")
    print(f"  results_json: {result['results_path']}")
    print("Generated files:")
    for name, path in result["generated_files"].items():
        print(f"  {name}: {path}")
    if result.get("sheets"):
        print("Processed sheets:")
        for sheet in result["sheets"]:
            print(f"  {sheet['sheet']}: {sheet['sheet_output_root']} ({sheet['curve_count']} curves)")
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    return 0


def main_stage_01() -> int:
    """Console entrypoint for Etapa 1."""

    return main(["stage_01"])


def main_stage_02() -> int:
    """Console entrypoint for Etapa 2."""

    return main(["stage_02"])


if __name__ == "__main__":
    raise SystemExit(main())

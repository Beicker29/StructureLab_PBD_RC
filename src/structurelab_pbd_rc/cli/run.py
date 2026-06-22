"""Command-line runner for StructureLab_PBD_RC workshops."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow "python -m structurelab_pbd_rc.cli.run ..." without external PYTHONPATH setup.
SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structurelab_pbd_rc.design.workshops.workshop_01_material_characterization import (
    DEFAULT_CONFIG_PATH as WORKSHOP_01_DEFAULT_CONFIG_PATH,
)
from structurelab_pbd_rc.design.workshops.workshop_01_material_characterization import run as run_workshop_01


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m structurelab_pbd_rc.cli.run",
        description="Run a StructureLab_PBD_RC workshop.",
    )
    parser.add_argument(
        "workshop",
        nargs="?",
        default="workshop_01",
        choices=["workshop_01"],
        help="Workshop id to run. Defaults to workshop_01.",
    )
    parser.add_argument(
        "--config",
        default=str(WORKSHOP_01_DEFAULT_CONFIG_PATH),
        help="Path to the workshop YAML config.",
    )
    parser.add_argument(
        "--output-root",
        default="outputs",
        help="Directory where workshop outputs are created.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a workshop from the command line."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    result = run_workshop_01(config_path=args.config, output_root=args.output_root)
    print(f"Prepared {result['workshop_id']} outputs:")
    print(f"  title: {result['config']['title']}")
    print(f"  config: {args.config}")
    for name, path in result["output_dirs"].items():
        print(f"  {name}: {path}")
    print(f"  results_json: {result['results_path']}")
    print("Generated files:")
    for name, path in result["generated_files"].items():
        print(f"  {name}: {path}")
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

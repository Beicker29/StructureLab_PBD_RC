"""Run Taller 5 workflow stub."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from structurelab_pbd_rc.design.workshops.workshop_05_beam_performance import DEFAULT_CONFIG_PATH, run


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Taller 5 outputs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output-root", default="outputs")
    args = parser.parse_args()
    result = run(config_path=args.config, output_root=args.output_root)
    print(f"Prepared {result['workshop_id']} outputs. Model logic is pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



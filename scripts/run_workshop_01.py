"""Run Taller 1 workflow."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from structurelab_pbd_rc.workflows.workshop_01_material_characterization import main


if __name__ == "__main__":
    raise SystemExit(main())


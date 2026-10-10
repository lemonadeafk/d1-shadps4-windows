"""capture-rig/scenario-checksum.py on Windows - the project's tool, unmodified, pointed at the
Windows d1guest (tools/d1guest_win.py) instead of the Linux one it loads for itself.

    python tools\\scenario_checksum_win.py now                 # the resident scenario (orbit at rest)
    python tools\\scenario_checksum_win.py controls            # its 4 controls; exit 2 on failure
    python tools\\scenario_checksum_win.py watch --hz 500      # every scenario-handle change

⚠ Use --hz 500 for a new world: the record is resident for ~100 ms while a world loads and fails
to instantiate, and --hz 50 misses it (d1-activity-host worlds.rs).
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from d1guest_win import d1guest  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "scenario_checksum", r"C:\d1server\d1preservation\capture-rig\scenario-checksum.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)
sc.d1guest = d1guest          # its functions look `d1guest` up as a module global at call time

if __name__ == "__main__":
    sys.exit(sc.main())

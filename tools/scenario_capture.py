"""Catch every scenario record the client resolves, with its per-bubble validity flags - the data
`scenario-checksum.py watch` summarises as one line. Uses that tool's own Scenario reader.

    python tools\\scenario_capture.py --hz 500 --for 600 > capture.log

For each new world it prints the D1_AH_* values (or launcher options) that publish it correctly:
checksum = record+0x0C (PRIVATE), bubble count = record+0x48, chosen = bubbles with valid flag > 0.
"""

import argparse
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenario_checksum_win import sc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--hz", type=float, default=500.0)
ap.add_argument("--for", dest="for_", type=float, default=600.0)
a = ap.parse_args()

proc, guest, ns = sc.open_client(argparse.Namespace(allow_dead=False))
mgr = guest.u64(sc.ACTIVITY_MANAGER_PTR)
print(f"watching activity_manager({mgr:#x}) + 0x278 at {a.hz} Hz", flush=True)
seen, last, period = set(), None, 1.0 / a.hz
end = time.time() + a.for_
while time.time() < end:
    try:
        tag, = struct.unpack("<I", proc.read(mgr + sc.SCENARIO_HANDLE_OFF, 4))
    except Exception as e:  # noqa: BLE001
        print(f"WATCH ENDED: {e}", flush=True)
        break
    if tag != last:
        last = tag
        stamp = time.strftime("%H:%M:%S")
        if tag == 0xFFFFFFFF:
            print(f"{stamp}  scenario handle cleared (-1)", flush=True)
        else:
            obj, why = guest.resolve_tag(tag)
            if obj is None:
                print(f"{stamp}  tag {tag:#010x}: {why}", flush=True)
            else:
                s = sc.Scenario(proc, tag, obj)
                print(f"{stamp}  {s.line()}", flush=True)
                # name_hash is NOT required to agree: city_tower's record carries the MAP name
                # ('city_tower') but the ACTIVITY's hash (0x545AEC79 = city_tower_default1,
                # design/activity-launch.md), so the tool's agreement test fails on a correct record.
                if tag not in seen and s.name:
                    seen.add(tag)
                    chosen = [i for i, (_h, ok) in enumerate(s.slice_hashes) if ok > 0]
                    rec = {"name": s.name, "scenario_tag": f"{tag:#010x}", "checksum": f"{s.checksums[0]:#010x}",
                           "public_checksum": f"{s.checksums[1]:#010x}", "bubble_count": s.bubble_count,
                           "bubbles": [{"i": i, "hash": f"{h:#010x}", "valid": ok}
                                       for i, (h, ok) in enumerate(s.slice_hashes)],
                           "chosen": chosen}
                    print("RECORD " + json.dumps(rec), flush=True)
                    # --world must be the ACTIVITY symbol that was published (e.g. city_tower_default1),
                    # which can differ from the record's map name printed here.
                    print(f"  => (map {s.name}) --checksum {s.checksums[0]:#010x} "
                          f"--bubbles {s.bubble_count} --chosen {','.join(map(str, chosen)) or '(none)'}",
                          flush=True)
    time.sleep(period)

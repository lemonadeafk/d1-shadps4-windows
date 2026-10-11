r"""Send a sensor value to the RUNNING game through the activity host's injection folder.

    python tools\inject_sensor.py <bubble> <group hash>:<sub>[:<value image hex>] [...]
    python tools\inject_sensor.py 3 0x8cc31436:55:<96 hex chars>     # Rahool's performance sensor

The frame is built by d1-oracle's `sensor_frame` example (kind, value schema and part 2 come from
the game's content) and dropped into `inject\` as a .udt5 file; the activity host
(D1_AH_SENSOR_INJECT_DIR, set by d1_launch.py --director) sends it on its next tick (~1 s) and
renames it .sent. Nothing is written into the game's memory.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
INJECT = os.path.join(os.path.dirname(HERE), "inject")
SENSOR_FRAME = r"C:\d1server\d1preservation\d1-server\target\release\examples\sensor_frame.exe"
WORLD = "0x80c7a005"          # city_tower_default1


def inject(bubble, entries, world=WORLD, wait=True):
    os.makedirs(INJECT, exist_ok=True)
    name = os.path.join(INJECT, "%d.udt5" % int(time.time() * 1000))
    r = subprocess.run([SENSOR_FRAME, world, str(bubble), name, *entries], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("sensor_frame failed: " + r.stdout + r.stderr)
    sent = name[:-5] + ".sent"
    end = time.time() + 15
    while wait and time.time() < end and not os.path.exists(sent):
        time.sleep(0.2)
    return os.path.exists(sent) or not wait


if __name__ == "__main__":
    ok = inject(int(sys.argv[1]), sys.argv[2:])
    print("sent" if ok else "NOT picked up - is the activity host running with D1_AH_SENSOR_INJECT_DIR?")

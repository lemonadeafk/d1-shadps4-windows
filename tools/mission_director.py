r"""Play the mission's scripted sequences (Ghost dialogue, music cues) from the server side.

    python tools\mission_director.py [--bubble 3] [--script wall]

Waits until the newest run reaches 'activity:in_world', then sends each sequence's value
through the activity host's injection folder (tools\inject_sensor.py) - the same udt-5 sensor
frames the host sends, nothing written into the game's memory.

A kind-5 sequence record (value 0x808029A1 {i32 start, u8 counter, ...}) plays when its counter
changes (setter FUN_0040BE80). NIGHT-NOTES section 47.
"""
import argparse
import glob
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inject_sensor  # noqa: E402

WORLD = "0x80cb800d"            # act_cosmo_m0_highway
DIALOGUE = "0x3c2f5ed5"         # group of seq_d_* / seq_m_* / seq_fallen_* records

# (seconds after the previous line, group, sub, name)
SCRIPTS = {
    # Inside the Wall: the Ghost's first objective lines, with the first music cue.
    "wall": [
        (4, DIALOGUE, 0, "seq_m_cue1"),
        (1, DIALOGUE, 3, "seq_d_o1_10"),
        (8, DIALOGUE, 4, "seq_d_o1_15"),
        (8, DIALOGUE, 5, "seq_d_o1_20"),
        (8, DIALOGUE, 6, "seq_d_o1_20b"),
        (8, DIALOGUE, 7, "seq_d_o1_20c"),
        (8, DIALOGUE, 8, "seq_d_o1_20d"),
        (10, DIALOGUE, 9, "seq_d_o2_10"),
    ],
}


def sequence_value(counter, start=0):
    img = bytearray(bytes.fromhex("ffffffffff000000" + "00" * 16 + "c59d1c81ff00ffff"))
    img[0:4] = struct.pack("<i", start)
    img[4] = counter & 0xFF
    return img.hex()


def newest_run():
    runs = sorted(glob.glob(r"C:\d1server\d1preservation\runs\*WIN-*"), key=os.path.getmtime)
    return runs[-1] if runs else None


def wait_in_world(timeout=900):
    t0 = time.time()
    seen = None
    while time.time() - t0 < timeout:
        run = newest_run()
        if run:
            log = os.path.join(run, "guest-stdout.log")
            try:
                with open(log, "rb") as f:
                    if b"Entering state 'activity:in_world'" in f.read():
                        return run
            except OSError:
                pass
            if run != seen:
                print("waiting for", os.path.basename(run), "to reach in_world")
                seen = run
        time.sleep(3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bubble", type=int, default=3)
    ap.add_argument("--script", default="wall", choices=sorted(SCRIPTS))
    ap.add_argument("--counter", type=int, default=1)
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()
    if not a.no_wait:
        run = wait_in_world()
        if not run:
            raise SystemExit("the game never reached in_world")
        print("in world:", os.path.basename(run))
        time.sleep(8)               # let the arrival frames land first
    for delay, group, sub, name in SCRIPTS[a.script]:
        time.sleep(delay)
        ok = inject_sensor.inject(a.bubble, ["%s:%d:%s" % (group, sub, sequence_value(a.counter))],
                                  world=WORLD)
        print(time.strftime("%H:%M:%S"), name, "sent" if ok else "NOT picked up")


if __name__ == "__main__":
    main()

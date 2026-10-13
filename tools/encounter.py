r"""Set an encounter objective's task states in the running game (test tool).

    python tools\encounter.py <world> <bubble> <group>:<sub> <state> [--tasks 0,1,5] [--epoch N]
    python tools\encounter.py 0x80cb804b 8 0x41d61614:1 2          # every task of obj_hive_dome_a01 -> 2

An encounter objective (kind 3, value 0x808004FA, 28 bytes) carries one state per task: the setter
FUN_001C20B0 compares each byte with the record's copy (rec+0x1E0 + i*0x1A) and, when it changed,
restarts that task in the new state (FUN_000E6730); +0x18 (u32) is kept at rec+0x450. The client
reports the same objective back as 3-bit groups (all 1 once its squads have registered).
What each state number does (spawn, wake, release a "frozen" squad ...) is what this tool is for:
NIGHT-NOTES section 91. Sent through the activity host's injection folder like any frame.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inject_sensor  # noqa: E402

TASKS = 24


def image(states, epoch=0):
    b = bytearray(28)
    for i, s in enumerate(states[:TASKS]):
        b[i] = s & 0xFF
    struct.pack_into("<I", b, 0x18, epoch)
    return bytes(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("world")
    ap.add_argument("bubble", type=int)
    ap.add_argument("ref", help="<group hash>:<sub> of the kind-3 objective")
    ap.add_argument("state", type=int)
    ap.add_argument("--tasks", help="only these task indices (others 1 = the reported resting state)")
    ap.add_argument("--epoch", type=int, default=0)
    a = ap.parse_args()
    states = [1] * TASKS
    for i in ([int(t) for t in a.tasks.split(",")] if a.tasks else range(TASKS)):
        states[i] = a.state
    img = image(states, a.epoch)
    print("value", img.hex())
    print("sent" if inject_sensor.inject(a.bubble, ["%s:%s" % (a.ref, img.hex())], world=a.world) else "NOT sent")


if __name__ == "__main__":
    main()

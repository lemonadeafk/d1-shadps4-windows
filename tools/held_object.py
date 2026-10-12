r"""Serve a "held object" record (kind 24, e.g. ho_ghostlight) to the running game.

    python tools\held_object.py <bubble> <group> <sub> [--on 1] [--seq N] [--selector players] [--mode M]

Value (schema 0x8080065C, 0x60 bytes): {bool on, u32 sequence, name ref, typed selector @+0x10
(tag) / +0x20 (body)}. The selector is one of 13 target-set types (table at [0x25BE898]);
0x808008F2 = the players (body = a 2-bit mode). NIGHT-NOTES section 55.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inject_sensor  # noqa: E402

SELECTORS = {"players": 0x808008F2, "none": 0xFFFFFFFF}


def image(on, seq, selector, mode, ref=None):
    b = bytearray(0x60)
    b[0] = 1 if on else 0
    b[4:8] = struct.pack("<I", seq)
    b[8:16] = bytes.fromhex("c59d1c81ff00ffff")         # null name ref
    if ref:                                             # (group hash, kind, sub) of the function record
        b[8:16] = struct.pack("<IBBH", ref[0], ref[1], 0, ref[2])
    b[0x10:0x14] = struct.pack("<I", selector)
    b[0x20] = mode
    return bytes(b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bubble", type=int)
    ap.add_argument("group")
    ap.add_argument("sub")
    ap.add_argument("--on", type=int, default=1)
    ap.add_argument("--seq", type=int, default=1)
    ap.add_argument("--selector", default="players", choices=sorted(SELECTORS))
    ap.add_argument("--mode", type=int, default=0)
    ap.add_argument("--world", default="0x80cb800d")
    ap.add_argument("--ref", default=None, help="name ref <group hex>:<kind>:<sub>, e.g. the kind-33 of_* record")
    a = ap.parse_args()
    sel = SELECTORS[a.selector]
    ref = None
    if a.ref:
        g, k, sub = a.ref.split(":")
        ref = (int(g, 16), int(k), int(sub))
    if sel != 0xFFFFFFFF:
        os.environ["D1_ORACLE_EXTRA_TAGS"] = hex(sel)
    ok = inject_sensor.inject(a.bubble, ["%s:%s:%s" % (a.group, a.sub, image(a.on, a.seq, sel, a.mode, ref).hex())],
                              world=a.world)
    print("sent" if ok else "NOT picked up")

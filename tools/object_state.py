r"""Serve a scripted object's state (kind-4 sensor value) to the running game.

    python tools\object_state.py <bubble> <group hash> <sub>[,<sub>...] [--seq N] [--ch0 v] [--ch1 v] [--ch2 v]

A kind-4 value (schema 0x808007D9) is {u32 sequence, i32 variant, bool exists, name ref,
u32 count @+0x20, 3 x 0x40-byte typed entries @+0x30}. The object's state component
(FUN_005D2280) reads entries whose type tag is 0x8080279A: three channels of
{u32 set-counter, u32 snap-counter, f32 value 0..1}; a counter that rises applies the value.
Sent through the activity host's injection folder - nothing is written into the game's memory.
NIGHT-NOTES section 53.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inject_sensor  # noqa: E402

STATE_TAG = 0x8080279A
BASE = os.path.join(os.path.dirname(HERE), "capture", "values", "object_exists.bin")


def image(seq, channels, exists=True):
    img = bytearray(open(BASE, "rb").read())
    img[0:4] = struct.pack("<I", seq)
    img[8] = 1 if exists else 0
    img[0x20:0x24] = struct.pack("<I", 1)                  # one typed entry
    img[0x30:0x34] = struct.pack("<I", STATE_TAG)
    body = b"".join(struct.pack("<IIf", seq, seq, v) for v in channels)
    img[0x40:0x40 + len(body)] = body
    return bytes(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bubble", type=int)
    ap.add_argument("group")
    ap.add_argument("subs")
    ap.add_argument("--seq", type=int, default=1)
    ap.add_argument("--ch0", type=float, default=1.0)
    ap.add_argument("--ch1", type=float, default=0.0)
    ap.add_argument("--ch2", type=float, default=0.0)
    ap.add_argument("--world", default="0x80cb800d")
    ap.add_argument("--gone", action="store_true", help="send exists = 0 (the object is removed)")
    a = ap.parse_args()
    os.environ["D1_ORACLE_EXTRA_TAGS"] = hex(STATE_TAG)
    img = image(a.seq, (a.ch0, a.ch1, a.ch2), not a.gone).hex()
    ok = inject_sensor.inject(a.bubble, ["%s:%s:%s" % (a.group, s, img) for s in a.subs.split(",")],
                              world=a.world)
    print("sent" if ok else "NOT picked up")


if __name__ == "__main__":
    main()

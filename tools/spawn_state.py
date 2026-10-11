r"""Read-only: why is the Guardian (not) in the world? Prints the spawn chain as the game holds it.

    python tools\spawn_state.py

Player-slot objects (kind 12): owner at +0x258, assigned block at +0x218 (+0x221 = spawn gate leg),
player handle +0x1F0. Player array element +0x50 = linked slot tag. player+0x0C = spawn word,
+0x644 = unit handle. Fade block at [0x2694B90]. Biped census from the sobject pool. No writes.
"""
import os, sys, struct, ctypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import argparse, contextlib, io
from d1guest_win import d1guest
ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
with contextlib.redirect_stdout(io.StringIO()):
    _, _, proc, g = d1guest.open_guest(ns)
B = g.base
q = lambda a: struct.unpack("<Q", proc.read(a, 8))[0]
d = lambda a: struct.unpack("<I", proc.read(a, 4))[0]


def resolve(t):
    t = ctypes.c_int32(t).value
    ecx = t >> 13
    esi = ((ecx & 0xffffffff) >> 18 | 0x3ff) & ecx & 0xffffffff
    e = q(q(B + 0x1A0B420)) + esi * 0x40
    p = q(e + 0x10) + (t & 0x1fff) * d(e + 0x30)
    return (p - (q(p + 8) & (ctypes.c_int32(d(e + 0x34)).value & 0xffffffffffffffff))) % 2**64


idx = struct.unpack("<H", proc.read(B + 0x25BE338, 2))[0]
hdr = B + 0x1ABCB80
world = q(idx * q(hdr + 0x10) + hdr + q(hdr) + 0x30)
kinds = {}
for i in range(struct.unpack("<H", proc.read(world + 0x510, 2))[0]):
    e = proc.read(world + 0x518 + i * 0x38, 0x38)
    kinds.setdefault(struct.unpack_from("<i", e, 0)[0], []).append(struct.unpack_from("<I", e, 8)[0])
print("simulation objects by kind:", {k: len(v) for k, v in sorted(kinds.items())})
for tag in kinds.get(12, [])[:40]:
    rec = resolve(tag)
    owner, handle = q(rec + 0x258), d(rec + 0x1F0)
    blk = proc.read(rec + 0x218, 0x10)
    if owner or handle not in (0, 0xFFFFFFFF) or any(blk):
        print(f"  slot {tag:#x}: owner {owner:#x} handle {handle:#x} block+0x218 {blk.hex()}")
for tag in kinds.get(16, []):
    rec = resolve(tag)
    print(f"  lifetime {tag:#x}: phase(+0x1AC) {d(rec + 0x1AC)}  tod {struct.unpack('<f', proc.read(rec + 0x680, 4))[0]:.2f}")
pe = q(B + 0x2670940 + 8)
print(f"player array element: handle {d(pe + 0x48):#x}  linked slot tag (+0x50) {d(pe + 0x50):#x}")
r = q(B + 0x2725700)
player = q(r + 8) + 0x80 if r else 0
if player:
    print(f"player[0] {player:#x}: spawn word +0x0C {d(player + 0x0C)}  unit handle +0x644 {d(player + 0x644):#x}")
fade = q(B + 0x2694B90)
if fade:
    print("fade block:", proc.read(fade, 0x20).hex())
ph = B + 0x26795E0
elems, stride, cap = q(ph + 8), d(ph + 0x10), d(ph + 0x14)
if 0 < stride < 0x1000 and 0 < cap <= 4096:
    raw = proc.read(elems, stride * cap)
    types = {}
    for i in range(cap):
        types[raw[i * stride + 8]] = types.get(raw[i * stride + 8], 0) + 1
    print("sobject types:", {k: v for k, v in sorted(types.items()) if k not in (0, 0xFF)})
    for i in range(cap):
        if raw[i * stride + 8] == 9:
            print(f"  biped #{i} at", tuple(round(x, 1) for x in struct.unpack_from("<fff", raw, i * stride + 0xE0)))

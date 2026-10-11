r"""Try every candidate performance on one NPC's performance sensor and report which ones the
game actually starts (the member record's +0xABC takes the value's sequence number when it does).

    python tools\perf_sweep.py <bubble> <group hash> <sensor sub> [--hold SECONDS] [--shots DIR]

Uses tools\inject_sensor.py (no memory writes; reads only).
"""
import argparse, ctypes, contextlib, io, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inject_sensor
from d1guest_win import d1guest

ap = argparse.ArgumentParser()
ap.add_argument("bubble", type=int); ap.add_argument("group"); ap.add_argument("sub", type=int)
ap.add_argument("--hold", type=float, default=2.5); ap.add_argument("--shots", default=None)
ap.add_argument("--only", default=None, help="comma-separated hex hashes")
a = ap.parse_args()

ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
with contextlib.redirect_stdout(io.StringIO()):
    _, _, proc, g = d1guest.open_guest(ns)
B = g.base
q = lambda x: struct.unpack("<Q", proc.read(x, 8))[0]
d = lambda x: struct.unpack("<I", proc.read(x, 4))[0]

def resolve(t):
    t = ctypes.c_int32(t).value; ecx = t >> 13
    esi = ((ecx & 0xffffffff) >> 18 | 0x3ff) & ecx & 0xffffffff
    e = q(q(B + 0x1A0B420)) + esi * 0x40
    p = q(e + 0x10) + (t & 0x1fff) * d(e + 0x30)
    return (p - (q(p + 8) & (ctypes.c_int32(d(e + 0x34)).value & 0xffffffffffffffff))) % 2**64

def members():
    idx = struct.unpack("<H", proc.read(B + 0x25BE338, 2))[0]; hdr = B + 0x1ABCB80
    w = q(idx * q(hdr + 0x10) + hdr + q(hdr) + 0x30)
    out = []
    for i in range(struct.unpack("<H", proc.read(w + 0x510, 2))[0]):
        e = proc.read(w + 0x518 + i * 0x38, 0x38)
        if struct.unpack_from("<i", e, 0)[0] == 2 and struct.unpack_from("<I", e, 8)[0] not in (0, 0xffffffff):
            out.append(resolve(struct.unpack_from("<I", e, 8)[0]))
    return out

root = os.path.dirname(HERE)
table = json.load(open(os.path.join(root, "capture", "tower-plaza-performance-hashes.json")))
cands = [l for grp in table.values() if not isinstance(grp, str) for key, l in grp if key == 0xafb11a12][0]
if a.only:
    cands = [int(x, 16) for x in a.only.split(",")]
default = open(os.path.join(root, "capture", "values", "default_kind40.bin"), "rb").read()
recs = members()
seq0 = max(d(r + 0xABC) for r in recs) & 0xffff
if a.shots:
    os.makedirs(a.shots, exist_ok=True); import gamewin
for n, h in enumerate(cands):
    seq = seq0 + n + 1
    v = bytearray(default); v[0:4] = struct.pack("<I", h); v[8:12] = struct.pack("<I", seq)
    before = [d(r + 0xABC) for r in recs]
    ok = inject_sensor.inject(a.bubble, [f"{a.group}:{a.sub}:{v.hex()}"])
    time.sleep(a.hold)
    after = [d(r + 0xABC) for r in recs]
    started = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
    if a.shots:
        gamewin.shot_bg(os.path.join(a.shots, f"{n:02d}-{h:08x}.png"))
    print(f"{n:2d} {h:#010x} seq {seq} sent={ok} started-on-members={started}", flush=True)

"""Find live instances of a C++ class in the running game by its RTTI name (Itanium ABI).

    python tools\\find_object.py c_time_of_day_game_system [--dump 0x200]

name string -> type_info (holds a pointer to the name at +8) -> vtable (type_info pointer at
vtable[-1]) -> objects whose first qword is that vtable. The emulator is frozen for the search.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1guest_win import d1guest  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("cls", help="class name, or a raw mangled name with --mangled")
ap.add_argument("--mangled", action="store_true")
ap.add_argument("--max-objects", type=int, default=16)
ap.add_argument("--dump", type=lambda s: int(s, 0), default=0x100)
a = ap.parse_args()

ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
syms, image, proc, guest = d1guest.open_guest(ns)
base = guest.base
mangled = (a.cls if a.mangled else f"{len(a.cls)}{a.cls}").encode() + b"\0"
blob = image.blob
# The name must start a string (preceded by NUL), not be the tail of e.g. "PN3cui...E".
i = blob.find(b"\0" + mangled)
i = i + 1 if i >= 0 else -1
if i < 0:
    raise SystemExit(f"{mangled!r} not in the eboot")
name_va = i - 0x4000
print(f"name {mangled[:-1].decode()} at vaddr {name_va:#x} -> host {base + name_va:#x}")
# Do NOT freeze the emulator for these scans: a multi-second stall trips the game's own hitch
# watchdog ("hitch detected: mainloop ...", RELEASE_VHALT on the BLOCK_DETECT thread, seen
# 2026-10-10). type_info/vtable addresses are static and objects are long-lived, so no freeze needed.
try:
    tis, _ = proc.find(struct.pack("<Q", base + name_va), limit=8)
    out = []
    for ti_name_slot in tis:
        ti = ti_name_slot - 8
        vt_hits, _ = proc.find(struct.pack("<Q", ti), limit=8)
        for vh in vt_hits:
            vtable = vh + 8
            objs, _ = proc.find(struct.pack("<Q", vtable), limit=a.max_objects)
            out.append((ti, vtable, [(o, proc.read(o, a.dump)) for o in objs]))
finally:
    pass
for ti, vtable, objs in out:
    print(f"type_info {ti:#x} (vaddr {ti - base:#x})  vtable {vtable:#x} (vaddr {vtable - base:#x})  {len(objs)} object(s)")
    for o, data in objs:
        print(f"  == object {o:#x}")
        for k in range(0, len(data), 16):
            q = struct.unpack_from("<2Q", data, k)
            f = struct.unpack_from("<4f", data, k)
            print(f"    +{k:#05x}  {q[0]:#018x} {q[1]:#018x}   " + " ".join(f"{v:11.4g}" for v in f))

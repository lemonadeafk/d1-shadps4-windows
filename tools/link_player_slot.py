r"""Diagnostic: give our player a player-slot object by hand, so the REAL spawn gate passes.

    python tools\link_player_slot.py            # in world via tools\nohook_inworld.py

What the activity host is expected to do and we do not serve yet (found 2026-10-10): the loaded
world holds 30 kind-12 simulation objects (schema 0x80802236), one per possible player. The client
(0x1195E0) links a player to the slot whose owner id (slot+0x258) equals the player's id: it stores
the slot's tag at player_array_element+0x50 (0x3011F0) and the player handle at slot+0x1F0
(0x1293D0). The spawn gate 0x414730 then needs slot+0x221 != 0 (0x1192A0 -> block at slot+0x218).
This writes that state for the first free slot and requests the spawn. A poke to identify the
target state, not a fix.
"""
import os, sys, struct, ctypes, time
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
slots = []
for i in range(struct.unpack("<H", proc.read(world + 0x510, 2))[0]):
    e = proc.read(world + 0x518 + i * 0x38, 0x38)
    if struct.unpack_from("<i", e, 0)[0] == 12:
        slots.append(struct.unpack_from("<I", e, 8)[0])
print(f"{len(slots)} player-slot objects in the world")
tag = slots[0]
rec = resolve(tag)
pe = q(B + 0x2670940 + 8)
handle = d(pe + 0x48)
print(f"slot tag {tag:#x} at {rec:#x}; player handle {handle:#x}; element+0x50 was {d(pe + 0x50):#x}")
if "--owner" in sys.argv:
    proc.write(rec + 0x258, struct.pack("<Q", int(sys.argv[sys.argv.index("--owner") + 1], 0)))
proc.write(rec + 0x1F0, struct.pack("<I", handle))
proc.write(rec + 0x220, b"\x01\x01")
proc.write(pe + 0x50, struct.pack("<I", tag))
r = q(B + 0x2725700)
player = q(r + 8) + 0x80
proc.write(player + 0x0C, struct.pack("<I", 3))
print("linked; spawn requested")
# The arrival fade stays up when the fly-in cinematic is skipped: clear it once the biped exists.
time.sleep(6)
fade = q(B + 0x2694B90)          # d1_inworld.FADE_PTR
if fade:
    for off in (0x00, 0x14, 0x18):
        proc.write(fade + off, struct.pack("<I", 0))
    print("fade cleared")
# Leaving the world must undo the link (see slot_guard.py) - keep a detached watcher for that.
import subprocess
subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "slot_guard.py")],
                 creationflags=0x00000008 | 0x00000200 | 0x01000000, close_fds=True,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
print("slot guard started")
# Arrive in daylight: the world's day starts at midnight (see time_of_day.py).
tod = q(B + 0x2943E40 + 8)
if tod and "--keep-night" not in sys.argv:
    proc.write(tod, struct.pack("<f", 0.45))
    print("time of day set to 0.45 (late morning)")

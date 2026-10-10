r"""Unlink the hand-linked player slot the moment the game leaves the world.

Started (detached) by link_player_slot.py. Returning to orbit, an idle kick or any other exit from
activity:in_world unloads the world's player-slot objects; the real client clears the player's
definition tag when that happens, but our link was written by hand, so the spawn gate keeps
dereferencing it and the client dies at eboot 0x119321 (seen 2026-10-10 on "hold triangle").
This tails the newest run's guest log and writes 0xFFFFFFFF back to player_array_element+0x50 as
soon as it sees "Leaving state 'activity:in_world'". Exits when the game does.
"""
import glob, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import argparse, contextlib, io
from d1guest_win import d1guest
ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
with contextlib.redirect_stdout(io.StringIO()):
    _, _, proc, g = d1guest.open_guest(ns)
B = g.base
runs = sorted(glob.glob(r"C:\d1server\d1preservation\runs\*"), key=os.path.getmtime)
log = os.path.join(runs[-1], "guest-stdout.log")
out = open(os.path.join(runs[-1], "slot-guard.log"), "a", buffering=1)
out.write(f"guarding {log}\n")
f = open(log, "rb")
f.seek(0, os.SEEK_END)
tail = b""
while proc.alive():
    chunk = f.read()
    if not chunk:
        time.sleep(0.02)
        continue
    tail = (tail + chunk)[-400:] if b"Leaving state 'activity:in_world'" not in tail + chunk else tail + chunk
    if b"Leaving state 'activity:in_world'" in tail:
        elem = struct.unpack("<Q", proc.read(B + 0x2670940 + 8, 8))[0]
        before = struct.unpack("<I", proc.read(elem + 0x50, 4))[0]
        proc.write(elem + 0x50, struct.pack("<I", 0xFFFFFFFF))
        player = struct.unpack("<Q", proc.read(struct.unpack("<Q", proc.read(B + 0x2725700, 8))[0] + 8, 8))[0] + 0x80
        out.write(f"left the world: element+0x50 {before:#x} -> 0xffffffff\n")
        break
out.write("done\n")

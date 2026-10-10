"""Find a 16-byte pattern in the live game's memory and print the floats around each hit.

    python tools\\find_consts.py <hex16> [--before 176] [--after 64]
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winproc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("hex")
ap.add_argument("--before", type=int, default=176)
ap.add_argument("--after", type=int, default=48)
ap.add_argument("--limit", type=int, default=12)
a = ap.parse_args()

pid = winproc.emu_pids()[0]
p = winproc.WinProc(pid)
sig = bytes.fromhex(a.hex)
# Per-frame constant rings are rewritten continuously: freeze the emulator so the search and the
# reads see one consistent snapshot.
# Scan live (a long freeze trips the game's hitch watchdog), then freeze only for the short reads
# and re-check each hit still holds the pattern.
hits, scanned = p.find(sig, executable_only=False, limit=a.limit)
p.suspend()
try:
    snaps = [(h, p.read(h - a.before, a.before + len(sig) + a.after)) for h in hits]
finally:
    p.resume()
snaps = [(h, d) for h, d in snaps if d[a.before:a.before + len(sig)] == sig]
print(f"{len(hits)} hit(s) in {scanned / 2**20:.0f} MiB (backing mirror excluded: {[hex(m) for m in p.excluded_mirrors]})")
for h, data in snaps:
    start = h - a.before
    print(f"== hit {h:#x}")
    for i in range(0, len(data), 16):
        fl = struct.unpack_from("<4f", data, i)
        mark = "  <== pattern" if start + i == h else ""
        print(f"  {start + i:#x} {i - a.before:+5d}  " + "  ".join(f"{v:12.5g}" for v in fl) + mark)

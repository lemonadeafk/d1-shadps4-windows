r"""Read or set the world's time of day (the "lighting is cooked" fix: it was simply night).

    python tools\time_of_day.py            # show it
    python tools\time_of_day.py 0.5        # noon   (0.0 = midnight, 0.25 = dawn, 0.75 = dusk)
    python tools\time_of_day.py now        # derive it from the real clock, as a server would

c_time_of_day_game_system (object at eboot 0x2943E40, state at [+8]): +0x00 float fraction of the
day, +0x04 float day length in seconds (7200 in the Tower), +0x08 float game seconds at the last
tick, +0x0C byte paused. Each tick adds elapsed/day_length to the fraction (0x8B47C0), so the day
starts at 0.0 = midnight when the activity starts and the Tower is black for the first half hour.
Only the fraction is written here; writing +0x08 too makes the next tick subtract it back out.
The real game sets it from the activity host: the lifetime-record setter 0x11DE30 calls 0x8B46C0
with record+0x680 when record+0x67C is set (same udt-5 value that carries the lifetime phase).
"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import argparse, contextlib, io
from d1guest_win import d1guest
ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
with contextlib.redirect_stdout(io.StringIO()):
    _, _, proc, g = d1guest.open_guest(ns)
state = struct.unpack("<Q", proc.read(g.base + 0x2943E40 + 8, 8))[0]
if not state:
    raise SystemExit("time-of-day state not allocated yet (not in a world?)")
frac, length, secs = struct.unpack("<3f", proc.read(state, 12))
print(f"time of day {frac:.3f} of a {length:.0f} s day ({frac * 24:.1f} h on a 24 h clock)")
if len(sys.argv) > 1:
    want = (time.time() % length) / length if sys.argv[1] == "now" else float(sys.argv[1]) % 1.0
    proc.write(state, struct.pack("<f", want))
    print(f"set to {want:.3f} ({want * 24:.1f} h)")

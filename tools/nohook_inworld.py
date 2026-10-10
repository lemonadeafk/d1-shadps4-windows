r"""Director launch -> in world with NO code hooks (diagnostic route, no Guardian).

    python tools\nohook_inworld.py          # run after launch_tower.py, while the game sits in
                                            # activity:initial_slice_set_loading

Finds the activity-lifetime record through the game's own getter (hardware breakpoint at
0x10C58F, RSI = &phase), writes phase 3, forces the rung-34 done mask to 0x7FF (harmless: task 9
has no side effects) and waits for activity:in_world. Nothing in the code segment is patched, so
the spawn gate (0x414730) keeps its real behaviour - which is the point: use this to study why it
refuses.
"""
import json, os, struct, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import argparse, contextlib, io
from d1guest_win import d1guest

ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
with contextlib.redirect_stdout(io.StringIO()):
    _, _, proc, g = d1guest.open_guest(ns)
B = g.base
regs = os.path.join(os.environ["TEMP"], "hwwatch_regs.json")
if os.path.exists(regs):
    os.remove(regs)
subprocess.run([sys.executable, os.path.join(HERE, "hwwatch.py"), f"{B + 0x10C58F:x}", "--exec", "--seconds", "3"],
               capture_output=True)
hits = json.load(open(regs))
phase = {h["Rsi"] for h in hits}
if len(phase) != 1:
    raise SystemExit(f"expected one lifetime record, saw {[hex(x) for x in phase]}")
phase = phase.pop()
print(f"base {B:#x}; lifetime phase byte at {phase:#x} = {proc.read(phase, 1).hex()}")
proc.write(phase, b"\x03")
proc.write(B + 0x26B5730, struct.pack("<I", 0x7FF))
proc.write(B + 0x26B5770, struct.pack("<I", 0))
print("phase = 3, done mask = 0x7FF, join counter = 0; waiting for the world to enable")
time.sleep(25)
print(f"PHASE_ADDR {phase:#x}")

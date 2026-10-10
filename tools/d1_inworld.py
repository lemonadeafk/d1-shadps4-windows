"""Orbit -> activity:in_world -> spawned Guardian, on Windows. A port of the sequence in
d1preservation design/GUARDIAN-IN-WORLD.md (the 2026-08-11 RADV corrections), driven by the
project's own d1guest through tools/d1guest_win.py.

⚠ Every write here is a CLIENT MODIFICATION (`synthetic_ancestor`, see d1guest.py "WRITES").
It identifies gates; it does not satisfy them. All writes are journalled to runs/guest-writes.jsonl.

Start the session with `Launch Destiny.cmd --inworld`, reach orbit, then:

    python tools\\d1_inworld.py            # whole sequence
    python tools\\d1_inworld.py --dry-run  # resolve every address, write nothing

Sequence (each step waits for the client to confirm the previous one):
  1. launch poke: activity id 407, goal = in_world, orbit debounce stamp = 0   (session-params.py)
  2. hold the fly-in curtain suppress, [0x26A33E8] byte0 = 1, every 2 s from here on
  3. wait for the rung-34 done mask at 0x26B5730 to read 0x1FF (tasks 0-8)
  4. freeze shadPS4, write both code hooks (0x10C500, 0x411E16), thaw
  5. done mask = 0x7FF, join counter 0x26B5770 = 0  -> physics_join -> activity:in_world
  6. wait for slice_set_transition_manager `fully_enabled` (spawning earlier never binds a camera)
  7. spawn word player[0]+0x0C = 3, then zero the fade block, then check player[0]+0x644 is a handle
Expect instability: the project's sessions lasted ~1 minute after spawn (crash at 0xBBDEDE).
2026-10-10 on Windows: playable on the Moon for ~2.5 min; summoning the Sparrow crashed the game
(write through a bad pointer at eboot 0x740CFF). Don't summon the Sparrow.
"""

import argparse
import glob
import json
import os
import re
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1guest_win import d1guest  # noqa: E402  (the project's d1guest with the Windows layer)

RUNS = r"C:\d1server\d1preservation\runs"

# session-params.py (0x773FC0 reproduction) and its launch_poke
MANAGER_PTR_VADDR = 0x26B1850
SESSION_STRIDE, INNER_STRIDE, STATE_OFFSET, PARAMS_OFFSET = 0x131C8, 0x98E0, 0x8C58, 0x6B38
ORBIT_HANDLER_VTABLE = 0x192F410          # c_world_controller_state_setup_orbit_handler (vaddr)
ORBIT_DEBOUNCE_OFFSET, GOAL_VALUE, ACTIVITY_ID = 0x38, 0xE4, 0xEA
RUNG_IN_WORLD = 0x24

# GUARDIAN-IN-WORLD.md §3-§5 and the top banner
SUPPRESS_PTR = 0x26A33E8
DONE_MASK, JOIN_CTR = 0x26B5730, 0x26B5770
PLAYER_ROOT = 0x2725700
FADE_PTR = 0x2694B90
SOBJECT_POOL = 0x26795E0
HOOKS = [  # (vaddr, original, patch, what)
    (0x10C500, "554889e541565348 83ec2049", "c70703000000b801000000c3",
     "FUN_0010C500 lifetime-state getter -> state 3, al=1"),
    (0x411E16, "0f8471030000", "909090909090",
     "FUN_00411830 per-player reject je -> NOPs"),
]


def log(msg):
    print(f"[inworld] {time.strftime('%H:%M:%S')} {msg}", flush=True)


class Session:
    def __init__(self, dry_run, activity, settle=15.0, no_spawn=False, skip_launch=False):
        self.skip_launch = skip_launch
        self.settle = settle
        self.no_spawn = no_spawn
        ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False,
                                full_scan=False, no_cache=False, allow_dead=False,
                                account_soid=None, require=3)
        _syms, _image, self.proc, self.guest = d1guest.open_guest(ns)
        d1guest.print_liveness(self.guest, ns, require=3)
        self.base = self.guest.base
        self.dry = dry_run
        self.activity = activity
        self.lock = threading.Lock()
        runs = sorted(glob.glob(os.path.join(RUNS, "*-WIN*")), key=os.path.getmtime)
        self.run = runs[-1] if runs else None
        self.guest_log = os.path.join(self.run, "guest-stdout.log") if self.run else None
        log(f"run folder {self.run}")

    # -- memory helpers (absolute addresses unless named v_) -------------------------------------
    def u32(self, addr):
        return struct.unpack("<I", self.proc.read(addr, 4))[0]

    def u64(self, addr):
        return struct.unpack("<Q", self.proc.read(addr, 8))[0]

    def write(self, addr, data, what):
        with self.lock:
            before = self.proc.read(addr, len(data))
            if self.dry:
                log(f"  DRY  {addr:#x} {before.hex()} -> {data.hex()}   {what}")
                return True
            self.proc.write(addr, data)
            after = self.proc.read(addr, len(data))
        ok = after == data
        self.journal(addr, before, after, what, ok)
        log(f"  {'OK ' if ok else 'BAD'}  {addr:#x} {before.hex()} -> {after.hex()}   {what}")
        return ok

    def journal(self, addr, before, after, what, ok, **extra):
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": self.proc.pid,
               "experiment": "d1_inworld", "host_addr": addr, "what": what,
               "before": before.hex(), "after": after.hex(), "readback_ok": ok,
               "platform": "windows", **extra}
        os.makedirs(os.path.dirname(d1guest.WRITE_JOURNAL), exist_ok=True)
        with open(d1guest.WRITE_JOURNAL, "a") as f:
            f.write(json.dumps(rec) + "\n")

    # -- the guest's own log --------------------------------------------------------------------
    def log_text(self):
        try:
            with open(self.guest_log, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def current_state(self):
        states = re.findall(r"Entering state '([^']+)' for reason '([^']+)'", self.log_text())
        return states[-1] if states else (None, None)

    def wait_for(self, what, predicate, timeout, every=1.0):
        end = time.time() + timeout
        last_state = None
        while time.time() < end:
            if not self.proc.alive():
                raise SystemExit(f"shadPS4 exited while waiting for {what}")
            state, reason = self.current_state()
            if state != last_state:
                log(f"  state: {state} ({reason})")
                last_state = state
            if state == "cleanup" and reason and reason.startswith("error."):
                raise SystemExit(f"client gave up: {reason} - see {self.guest_log}")
            if predicate():
                return True
            time.sleep(every)
        raise SystemExit(f"timed out after {timeout:.0f} s waiting for {what}")

    # -- steps ----------------------------------------------------------------------------------
    def session_params(self):
        manager = self.u64(self.base + MANAGER_PTR_VADDR)
        if not manager or self.proc.read(manager, 1)[0] == 0:
            raise SystemExit("session manager not valid yet")
        slot = manager
        inner = struct.unpack("<i", self.proc.read(slot + 8, 4))[0] * INNER_STRIDE
        state = self.u32(inner + slot + STATE_OFFSET)
        if state > 0xA or not (0x7F0 >> state) & 1:
            raise SystemExit(f"session 0 state {state} outside 4..10 - refusing")
        return inner + slot + PARAMS_OFFSET

    def launch(self):
        state, _ = self.current_state()
        if state != "setup:orbit":
            raise SystemExit(f"refusing to launch: the client is in {state!r}, not 'setup:orbit'")
        params = self.session_params()
        vt = struct.pack("<Q", self.base + ORBIT_HANDLER_VTABLE)
        log("scanning for the orbit handler (by vtable pointer)...")
        hits, scanned = self.proc.find(vt, executable_only=False, limit=4)
        if len(hits) != 1:
            raise SystemExit(f"REFUSING: expected exactly 1 orbit handler, found {len(hits)} "
                             f"{[hex(h) for h in hits]} in {scanned / 2**20:.0f} MiB")
        handler = hits[0]
        log(f"orbit handler {handler:#x}, session params {params:#x}")
        ok = self.write(params + 0x9B8 + ACTIVITY_ID, struct.pack("<H", self.activity), f"activity id {self.activity}")
        ok &= self.write(params + GOAL_VALUE, struct.pack("<I", RUNG_IN_WORLD), "goal_a = in_world")
        ok &= self.write(handler + ORBIT_DEBOUNCE_OFFSET, struct.pack("<Q", 0), "orbit debounce stamp = 0")
        if not ok:
            raise SystemExit("a launch write did not read back")

    def hold_suppress(self, stop):
        """GUARDIAN-IN-WORLD.md correction 2: the curtain suppress decays and must be HELD."""
        n = 0
        while not stop.is_set() and self.proc.alive():
            try:
                p = self.u64(self.base + SUPPRESS_PTR)
                if p:
                    with self.lock:
                        if self.proc.read(p, 1) != b"\x01" and not self.dry:
                            self.proc.write(p, b"\x01")
                            n += 1
            except Exception as e:  # noqa: BLE001 - the client may be mid-teardown
                log(f"  suppress hold: {e}")
            stop.wait(2.0)
        log(f"suppress hold stopped after {n} re-poke(s)")

    def hooks(self):
        plan = []
        for vaddr, orig, patch, what in HOOKS:
            orig, patch = bytes.fromhex(orig.replace(" ", "")), bytes.fromhex(patch)
            cur = self.proc.read(self.base + vaddr, len(orig))
            if cur == patch[:len(orig)]:
                log(f"  hook already present at {vaddr:#x}")
                continue
            if cur != orig:
                raise SystemExit(f"REFUSING hooks: {vaddr:#x} holds {cur.hex()}, expected {orig.hex()}")
            plan.append((self.base + vaddr, cur, patch, what))
        if self.dry or not plan:
            for addr, cur, patch, what in plan:
                log(f"  DRY  {addr:#x} {cur.hex()} -> {patch.hex()}   {what}")
            return
        with self.lock:
            self.proc.suspend()
            t0 = time.perf_counter()
            try:
                for addr, _cur, patch, _what in plan:
                    self.proc.write(addr, patch)
                afters = [self.proc.read(addr, len(patch)) for addr, _c, patch, _w in plan]
            finally:
                self.proc.resume()
        ms = (time.perf_counter() - t0) * 1000
        for (addr, cur, patch, what), after in zip(plan, afters):
            ok = after == patch
            self.journal(addr, cur, after, what, ok, frozen=True)
            log(f"  {'OK ' if ok else 'BAD'}  {addr:#x} {cur.hex()} -> {after.hex()}   {what}")
        log(f"  hooks written with the emulator frozen for {ms:.1f} ms")

    def bipeds(self):
        """sobjects pool (GUARDIAN-IN-WORLD.md §5): header IN eboot BSS at 0x26795E0 - +0x08 element
        base, +0x10 stride (0xF0), +0x14 capacity (1500); element type = byte +0x08, 9 = biped,
        position floats at +0xE0. Measured live 2026-10-10 (header bytes ...f0000000 dc050000)."""
        hdr = self.base + SOBJECT_POOL
        elems, stride, cap = self.u64(hdr + 8), self.u32(hdr + 0x10), self.u32(hdr + 0x14)
        if not (0 < stride < 0x1000 and 0 < cap <= 4096):
            return None
        found = []
        for i in range(cap):
            e = elems + i * stride
            if self.proc.read(e + 8, 1)[0] == 9:
                found.append((i, struct.unpack("<fff", self.proc.read(e + 0xE0, 12))))
        return found

    def player0(self):
        p = self.u64(self.base + PLAYER_ROOT)
        return self.u64(p + 8) + 0x80 if p else 0

    def run_all(self):
        stop = threading.Event()
        if self.skip_launch:
            # The player launched from the Director (tools\launch_tower.py): the game is already
            # past orbit on its own, so the launch poke is neither needed nor valid.
            log(f"--skip-launch: client is in {self.current_state()[0]!r}; not poking a launch")
        else:
            self.launch()
        holder = threading.Thread(target=self.hold_suppress, args=(stop,), daemon=True)
        holder.start()
        try:
            log("waiting for the rung-34 done mask to reach 0x1FF (tasks 0-8; ~2-5 min)")
            last = [None]

            def mask_ready():
                m = self.u32(self.base + DONE_MASK)
                if m != last[0]:
                    log(f"  done mask {m:#x}")
                    last[0] = m
                return m & 0x1FF == 0x1FF
            self.wait_for("done mask 0x1FF", mask_ready, timeout=900, every=1.0)

            log("hooks (freeze-write-thaw)")
            self.hooks()
            self.write(self.base + DONE_MASK, struct.pack("<I", 0x7FF), "done mask = 0x7FF (skip tasks 9/10)")
            self.write(self.base + JOIN_CTR, struct.pack("<I", 0), "join counter = 0 (rung 35 -> 36)")

            log("waiting for activity:in_world")
            self.wait_for("activity:in_world", lambda: self.current_state()[0] == "activity:in_world",
                          timeout=300)
            # Only a `fully_enabled` logged AFTER in_world counts - orbit's own load logs one too, and
            # matching that made the 2026-10-10 01:51 run spawn in the same second the world enabled:
            # a biped was built (type 9 at -47.2,38.3,7.7) but player+0x644 never bound.
            log("waiting for slice_set_transition_manager -> fully_enabled (after in_world)")

            def enabled_after_in_world():
                text = self.log_text()
                i = text.rfind("Entering state 'activity:in_world'")
                return i >= 0 and "to 'fully_enabled'" in text[i:]
            self.wait_for("fully_enabled", enabled_after_in_world, timeout=600)
            log(f"world fully enabled; letting instantiation settle for {self.settle:.0f} s before the spawn")
            time.sleep(self.settle)

            if self.no_spawn:
                # The forced spawn is what crashes (~1-3 min later, 0xBBDEDE / 0x740CFF). For
                # reading world state, stop here: in_world and fully enabled, no Guardian.
                log("--no-spawn: in world, no Guardian; holding the curtain suppress (Ctrl+C to stop)")
                while self.proc.alive():
                    time.sleep(1)
                log("shadPS4 exited")
                return
            player = self.player0()
            if not player:
                raise SystemExit("player root is NULL")
            log(f"player[0] at {player:#x}, handle before spawn {self.u32(player + 0x644):#x}")
            self.write(player + 0x0C, struct.pack("<I", 3), "spawn word player[0]+0x0C = 3")
            fade = self.u64(self.base + FADE_PTR)
            if fade:
                for off, what in ((0x00, "count"), (0x14, "mode"), (0x18, "alpha")):
                    self.write(fade + off, struct.pack("<I", 0), f"fade block +{off:#x} {what} = 0")
            time.sleep(10)
            found = self.bipeds()
            log("biped census: " + ("pool header unreadable" if found is None else
                                    f"{len(found)} type-9 biped(s) "
                                    + ", ".join(f"slot {i} at ({x:.1f}, {y:.1f}, {z:.1f})"
                                                for i, (x, y, z) in found)))
            handle = self.u32(player + 0x644)
            # GUARDIAN-IN-WORLD.md treats +0x644 as the camera-bind proof. On Windows 2026-10-10 it
            # read 0 while the operator was ON SCREEN and in control on the Moon, so it is reported,
            # not used as a verdict.
            log(f"player[0]+0x644 = {handle:#x} (informational: read 0 on a run that was playable)")
            log("holding the curtain suppress; press Ctrl+C here to stop (the game keeps running)")
            while self.proc.alive():
                time.sleep(1)
            log("shadPS4 exited")
        except KeyboardInterrupt:
            log("stopped by you")
        finally:
            stop.set()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="resolve and show; write nothing")
    ap.add_argument("--activity", type=int, default=407, help="activity id (407 = the proven pvp_moonbase mode)")
    ap.add_argument("--settle", type=float, default=15.0,
                    help="seconds to wait after fully_enabled before the spawn word (default 15)")
    ap.add_argument("--no-spawn", action="store_true", help="stop once in world; skip the (crash-prone) spawn")
    ap.add_argument("--skip-launch", action="store_true",
                    help="the game was launched from the Director; do everything except the launch poke")
    args = ap.parse_args()
    s = Session(args.dry_run, args.activity, args.settle, args.no_spawn, args.skip_launch)
    if args.dry_run:
        s.launch()
        s.hooks()
        p = s.player0()
        log(f"player[0] would be {p:#x}" if p else "player root NULL (expected in orbit)")
        return 0
    s.run_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""d1guest on Windows - the project's capture-rig/d1guest.py, unmodified, with the OS layer swapped.

Loads C:\\d1server\\d1preservation\\capture-rig\\d1guest.py as a module and replaces only:
  * emu_pids / Proc   -> winproc (ReadProcessMemory / WriteProcessMemory / VirtualQueryEx)
  * SYMBOLS           -> tools/guest-symbols.win.json (the real file was never published)
  * BASE_CACHE        -> %TEMP%\\d1guest-base.json (was /tmp)
Base recovery, its three controls, the liveness ladder and the poke journal are the project's code.

    python tools\\d1guest_win.py base
    python tools\\d1guest_win.py live
    python tools\\d1guest_win.py read fade_block_ptr --deref --len 0x20
    python tools\\d1guest_win.py poke 0x26A33E8 1 --deref --type u8 --experiment NAME --confirm

Extra, Windows-only:
    python tools\\d1guest_win.py freeze-poke <vaddr>=<hexbytes> [...] --experiment NAME --confirm
        suspends shadPS4, writes every patch, resumes - the freeze-write-thaw GUARDIAN-IN-WORLD.md
        requires for multi-byte hook writes (a torn write on a hot function crashed their run 121021).
"""

import importlib.util
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = r"C:\d1server\d1preservation"
sys.path.insert(0, HERE)
import winproc  # noqa: E402

spec = importlib.util.spec_from_file_location("d1guest", os.path.join(REPO, "capture-rig", "d1guest.py"))
d1guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d1guest)

winproc.WinProc.Dead = d1guest.Dead
d1guest.Proc = winproc.WinProc
d1guest.emu_pids = winproc.emu_pids
d1guest.SYMBOLS = os.path.join(HERE, "guest-symbols.win.json")
d1guest.BASE_CACHE = os.path.join(tempfile.gettempdir(), "d1guest-base.json")
# The Linux message names pgrep; say what this port actually looked for.
_orig_open_guest = d1guest.open_guest


def _open_guest(args, need_base=True):
    if not winproc.emu_pids():
        raise SystemExit("no running shadps4.exe - a runtime read with no runtime is an ERROR, "
                         "not an empty result")
    return _orig_open_guest(args, need_base)


d1guest.open_guest = _open_guest

SHAD_LOG = os.path.join(os.environ.get("APPDATA", ""), "shadPS4", "log", "shad_log.txt")
_orig_recover_base = d1guest.recover_base


def _recover_base(proc, image, syms, **kw):
    """The project's three controls, then a fourth only Windows can offer: shadPS4's own log line
    `Loading module eboot.bin to 0x...` must name the same base. It is written by the loader, not
    derived from any byte we scanned, so it is independent of all three."""
    base, ctl = _orig_recover_base(proc, image, syms, **kw)
    mirrors = getattr(proc, "excluded_mirrors", None)
    if mirrors:
        ctl.lines.append(f"  note: skipped shadPS4's backing-memory mirror at "
                         f"{', '.join(hex(m) for m in mirrors)} (every guest byte appears there too)")
    logged = None
    try:
        with open(SHAD_LOG, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "Loading module eboot.bin to " in line:
                    logged = int(line.rsplit(" ", 1)[1], 16)
                    break
    except OSError:
        pass
    if base is None:
        return base, ctl
    if logged is None:
        ctl.check("shadPS4 log", False, f"no 'Loading module eboot.bin' line in {SHAD_LOG}")
    else:
        ctl.check("shadPS4 log", logged == base,
                  f"loader logged eboot.bin at {logged:#x} - "
                  + ("same base" if logged == base else "DIFFERENT base (stale log or wrong scan)"))
    return (base if ctl.ok else None), ctl


d1guest.recover_base = _recover_base


def freeze_poke(argv):
    """freeze-poke <vaddr>=<hex> ... --experiment NAME --confirm [--abs]"""
    import argparse
    ap = argparse.ArgumentParser(prog="d1guest_win.py freeze-poke")
    ap.add_argument("writes", nargs="+", metavar="VADDR=HEXBYTES")
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--confirm", action="store_true", required=True)
    ap.add_argument("--abs", action="store_true", help="addresses are host addresses, not eboot vaddrs")
    a = ap.parse_args(argv)
    ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False,
                            full_scan=False, no_cache=False)
    syms, image, proc, guest = d1guest.open_guest(ns)
    plan = []
    for w in a.writes:
        target, _, hexbytes = w.partition("=")
        vaddr, _sym = syms.resolve(target)
        data = bytes.fromhex(hexbytes)
        plan.append((target, vaddr, vaddr if a.abs else guest.base + vaddr, data))
    proc.suspend()
    t0 = time.perf_counter()
    try:
        befores = [proc.read(addr, len(data)) for _t, _v, addr, data in plan]
        for _t, _v, addr, data in plan:
            proc.write(addr, data)
        afters = [proc.read(addr, len(data)) for _t, _v, addr, data in plan]
    finally:
        proc.resume()
    frozen_ms = (time.perf_counter() - t0) * 1000
    print("=" * 96)
    print("⚠ CLIENT MODIFICATION (freeze-write-thaw). Everything downstream is `synthetic_ancestor`.")
    print("=" * 96)
    ok_all = True
    os.makedirs(os.path.dirname(d1guest.WRITE_JOURNAL), exist_ok=True)
    with open(d1guest.WRITE_JOURNAL, "a") as f:
        for (target, vaddr, addr, data), before, after in zip(plan, befores, afters):
            ok = after == data
            ok_all &= ok
            print(f"  {target:<24} host {addr:#x}  {before.hex()} -> {after.hex()}  "
                  f"{'OK' if ok else '*** READBACK MISMATCH ***'}")
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": proc.pid,
                                "experiment": a.experiment, "target": target, "vaddr": vaddr,
                                "host_addr": addr, "before": before.hex(), "after": after.hex(),
                                "frozen": True, "readback_ok": ok, "platform": "windows"}) + "\n")
    print(f"  process frozen for {frozen_ms:.1f} ms; journalled to {d1guest.WRITE_JOURNAL}")
    return 0 if ok_all else 2


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "freeze-poke":
        sys.exit(freeze_poke(sys.argv[2:]))
    sys.exit(d1guest.main())

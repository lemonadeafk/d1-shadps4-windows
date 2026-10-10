r"""Stay attached to the game and report the access violation that kills it.

    python tools\crashwatch.py [--minutes 10]

shadPS4 only logs "Unhandled Exception code 0xc0000005 at <rip>". This attaches as a debugger,
passes every exception straight back (the emulator uses first-chance faults for its own memory
tracking), and remembers the last few access violations raised from EBOOT code together with the
registers, the faulting address and the eboot return addresses on the stack. When the process
exits it prints them: the last one is the crash.
"""
import argparse, collections, ctypes, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hwwatch as hw
import winproc
import contextlib, io
from d1guest_win import d1guest

ap = argparse.ArgumentParser()
ap.add_argument("--minutes", type=float, default=10)
a = ap.parse_args()
ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
with contextlib.redirect_stdout(io.StringIO()):
    _, _, proc, g = d1guest.open_guest(ns)
B = g.base
pid = winproc.emu_pids()[0]
k32 = hw.k32
k32.DebugSetProcessKillOnExit.argtypes = [hw.wintypes.BOOL]
if not k32.DebugActiveProcess(pid):
    raise SystemExit(f"DebugActiveProcess failed: {ctypes.get_last_error()}")
k32.DebugSetProcessKillOnExit(False)
ring = collections.deque(maxlen=6)
ev = hw.DEBUG_EVENT()
end = time.time() + a.minutes * 60
REGS = ("Rax", "Rbx", "Rcx", "Rdx", "Rsi", "Rdi", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15", "Rsp", "Rbp")
n_av = 0
exited = False
print(f"attached to pid {pid}, eboot base {B:#x}; waiting for the crash (max {a.minutes:g} min)", flush=True)
while time.time() < end:
    if not k32.WaitForDebugEvent(ctypes.byref(ev), 200):
        continue
    status = hw.DBG_CONTINUE
    code = ev.dwDebugEventCode
    if code == hw.EXCEPTION_DEBUG_EVENT:
        rec = ev.u.Exception.ExceptionRecord
        if rec.ExceptionCode == hw.EXCEPTION_BREAKPOINT:
            pass
        else:
            status = hw.DBG_EXCEPTION_NOT_HANDLED
            rip = rec.ExceptionAddress or 0
            if rec.ExceptionCode == 0xC0000005 and B <= rip < B + 0x1900000:
                n_av += 1
                h = k32.OpenThread(hw.THREAD_ALL, False, ev.dwThreadId)
                keep, ctx = hw.aligned_context()
                ctx.ContextFlags = hw.CONTEXT_AMD64 | 0x3
                k32.GetThreadContext(h, ctypes.byref(ctx))
                stack = hw.winproc_read(pid, ctx.Rsp, 8 * 160) or b""
                rets = [v for (v,) in __import__("struct").iter_unpack("<Q", stack) if B <= v < B + 0x1900000]
                ring.append({"rip": rip - B, "access": rec.ExceptionInformation[0], "addr": rec.ExceptionInformation[1],
                             "first": ev.u.Exception.dwFirstChance,
                             "regs": {r: getattr(ctx, r) for r in REGS}, "rets": [v - B for v in rets[:14]]})
                k32.CloseHandle(h)
    elif code == hw.EXIT_PROCESS_DEBUG_EVENT:
        exited = True
        k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
        break
    k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
if not exited:
    k32.DebugActiveProcessStop(pid)
print(f"{'process exited' if exited else 'time up, detached'}; {n_av} eboot access violation(s) seen")
for i, e in enumerate(ring):
    last = " <== LAST" if i == len(ring) - 1 else ""
    print(f"-- AV at eboot {e['rip']:#x} {'write' if e['access'] else 'read'} of {e['addr']:#x} first-chance={e['first']}{last}")
    print("   " + "  ".join(f"{k.lower()}={v:#x}" for k, v in e["regs"].items()))
    print("   stack eboot addrs: " + " ".join(f"{v:#x}" for v in e["rets"]))

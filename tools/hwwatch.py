"""Hardware data watchpoint on the running game: which guest code touches an address?

    python tools\\hwwatch.py <hex addr> [--len 4] [--seconds 10] [--write-only] [--press n]

Attaches as a debugger, puts the address in DR0 on every thread, collects the instruction pointer
of every access (reported as eboot vaddrs), then clears the registers and detaches - the game keeps
running. With --press KEY it taps that key halfway through and splits the hits before/after.

shadPS4 uses first-chance exceptions for its own memory tracking; those are passed straight back
(DBG_EXCEPTION_NOT_HANDLED), so the emulator handles them as usual. Keep windows short: every
exception now round-trips through this process.
"""
import argparse
import collections
import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winproc  # noqa: E402

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
EXCEPTION_DEBUG_EVENT, CREATE_THREAD_DEBUG_EVENT, CREATE_PROCESS_DEBUG_EVENT = 1, 2, 3
EXIT_PROCESS_DEBUG_EVENT, LOAD_DLL_DEBUG_EVENT = 5, 6
EXCEPTION_SINGLE_STEP, EXCEPTION_BREAKPOINT = 0x80000004, 0x80000003
CONTEXT_AMD64 = 0x00100000
CONTEXT_CONTROL = CONTEXT_AMD64 | 0x1
CONTEXT_DEBUG_REGISTERS = CONTEXT_AMD64 | 0x10
THREAD_ALL = 0x001F03FF
TH32CS_SNAPTHREAD = 0x4


class M128(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint64), ("hi", ctypes.c_uint64)]


class CONTEXT(ctypes.Structure):
    _pack_ = 16
    _fields_ = [("P1Home", ctypes.c_uint64), ("P2Home", ctypes.c_uint64), ("P3Home", ctypes.c_uint64),
                ("P4Home", ctypes.c_uint64), ("P5Home", ctypes.c_uint64), ("P6Home", ctypes.c_uint64),
                ("ContextFlags", wintypes.DWORD), ("MxCsr", wintypes.DWORD),
                ("SegCs", wintypes.WORD), ("SegDs", wintypes.WORD), ("SegEs", wintypes.WORD),
                ("SegFs", wintypes.WORD), ("SegGs", wintypes.WORD), ("SegSs", wintypes.WORD),
                ("EFlags", wintypes.DWORD),
                ("Dr0", ctypes.c_uint64), ("Dr1", ctypes.c_uint64), ("Dr2", ctypes.c_uint64),
                ("Dr3", ctypes.c_uint64), ("Dr6", ctypes.c_uint64), ("Dr7", ctypes.c_uint64),
                ("Rax", ctypes.c_uint64), ("Rcx", ctypes.c_uint64), ("Rdx", ctypes.c_uint64),
                ("Rbx", ctypes.c_uint64), ("Rsp", ctypes.c_uint64), ("Rbp", ctypes.c_uint64),
                ("Rsi", ctypes.c_uint64), ("Rdi", ctypes.c_uint64), ("R8", ctypes.c_uint64),
                ("R9", ctypes.c_uint64), ("R10", ctypes.c_uint64), ("R11", ctypes.c_uint64),
                ("R12", ctypes.c_uint64), ("R13", ctypes.c_uint64), ("R14", ctypes.c_uint64),
                ("R15", ctypes.c_uint64), ("Rip", ctypes.c_uint64),
                ("FltSave", ctypes.c_byte * 512),
                ("VectorRegister", M128 * 26), ("VectorControl", ctypes.c_uint64),
                ("DebugControl", ctypes.c_uint64), ("LastBranchToRip", ctypes.c_uint64),
                ("LastBranchFromRip", ctypes.c_uint64), ("LastExceptionToRip", ctypes.c_uint64),
                ("LastExceptionFromRip", ctypes.c_uint64)]


class EXCEPTION_RECORD(ctypes.Structure):
    _fields_ = [("ExceptionCode", wintypes.DWORD), ("ExceptionFlags", wintypes.DWORD),
                ("ExceptionRecord", ctypes.c_void_p), ("ExceptionAddress", ctypes.c_void_p),
                ("NumberParameters", wintypes.DWORD), ("ExceptionInformation", ctypes.c_uint64 * 15)]


class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", wintypes.DWORD)]


class CREATE_THREAD_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("hThread", wintypes.HANDLE), ("lpThreadLocalBase", ctypes.c_void_p),
                ("lpStartAddress", ctypes.c_void_p)]


class U(ctypes.Union):
    _fields_ = [("Exception", EXCEPTION_DEBUG_INFO), ("CreateThread", CREATE_THREAD_DEBUG_INFO),
                ("raw", ctypes.c_byte * 160)]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [("dwDebugEventCode", wintypes.DWORD), ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD), ("u", U)]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]


def aligned_context():
    buf = ctypes.create_string_buffer(ctypes.sizeof(CONTEXT) + 16)
    addr = (ctypes.addressof(buf) + 15) & ~15
    return buf, CONTEXT.from_address(addr)


def threads_of(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def set_dr(hthread, addr, length, rw):
    keep, ctx = aligned_context()
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS
    if not k32.GetThreadContext(hthread, ctypes.byref(ctx)):
        return False
    lenbits = {1: 0, 2: 1, 8: 2, 4: 3}[length]
    if addr:
        ctx.Dr0 = addr
        ctx.Dr7 = (ctx.Dr7 & ~0x000F0003) | 0x1 | (rw << 16) | (lenbits << 18)
    else:
        ctx.Dr0 = 0
        ctx.Dr7 &= ~0x000F0003
    ctx.Dr6 = 0
    return bool(k32.SetThreadContext(hthread, ctypes.byref(ctx)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addr", type=lambda s: int(s, 16))
    ap.add_argument("--len", type=int, default=4)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--write-only", action="store_true")
    ap.add_argument("--press", default=None)
    ap.add_argument("--exec", action="store_true", help="execution breakpoint (addr = instruction)")
    ap.add_argument("--dump", action="append", metavar="REG:HEXLEN",
                    help="with --exec: also record the memory a register points at (e.g. R8:80)")
    ap.add_argument("--value", default=None, help="hex u32: keep a write hit only if the address now holds it")
    a = ap.parse_args()
    pid = winproc.emu_pids()[0]
    base = int(open(os.path.join(os.path.dirname(__file__), "..", "base.txt")).read(), 16) \
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "base.txt")) else None
    rw = 0 if a.exec else (1 if a.write_only else 3)
    if a.exec:
        a.len = 1

    k32.DebugSetProcessKillOnExit.argtypes = [wintypes.BOOL]
    if not k32.DebugActiveProcess(pid):
        raise SystemExit(f"DebugActiveProcess failed: {ctypes.get_last_error()}")
    k32.DebugSetProcessKillOnExit(False)
    handles = {}
    hits = collections.Counter()
    marks = {"phase": "before"}
    split = {"before": collections.Counter(), "after": collections.Counter()}
    regs = {}

    def arm(tid, h):
        handles[tid] = h
        set_dr(h, a.addr, a.len, rw)

    if a.press:
        def presser():
            time.sleep(a.seconds / 2)
            marks["phase"] = "after"
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "gamewin.py"), "key", a.press])
        threading.Thread(target=presser, daemon=True).start()

    ev = DEBUG_EVENT()
    end = time.time() + a.seconds
    armed_all = False
    try:
        while time.time() < end:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 100):
                continue
            code = ev.dwDebugEventCode
            status = DBG_CONTINUE
            if code == CREATE_PROCESS_DEBUG_EVENT:
                pass
            elif code == CREATE_THREAD_DEBUG_EVENT:
                h = k32.OpenThread(THREAD_ALL, False, ev.dwThreadId)
                if h:
                    arm(ev.dwThreadId, h)
            elif code == EXCEPTION_DEBUG_EVENT:
                rec = ev.u.Exception.ExceptionRecord
                if rec.ExceptionCode == EXCEPTION_SINGLE_STEP:
                    h = handles.get(ev.dwThreadId) or k32.OpenThread(THREAD_ALL, False, ev.dwThreadId)
                    keep, ctx = aligned_context()
                    ctx.ContextFlags = CONTEXT_CONTROL | CONTEXT_DEBUG_REGISTERS | CONTEXT_AMD64 | 0x2
                    k32.GetThreadContext(h, ctypes.byref(ctx))
                    want = int(a.value, 16) if a.value else None
                    got = None
                    if want is not None and ctx.Dr6 & 1:
                        raw = winproc_read(pid, a.addr, 4)
                        got = int.from_bytes(raw, "little") if raw else None
                    if ctx.Dr6 & 1 and want is not None and got != want:
                        ctx.Dr6 = 0
                        k32.SetThreadContext(h, ctypes.byref(ctx))
                    elif ctx.Dr6 & 1:
                        rip = ctx.Rip
                        split[marks["phase"]][rip] += 1
                        if rip not in regs:
                            regs[rip] = (ctx.Rsp, [ctypes.c_uint64.from_buffer_copy(
                                bytes(winproc_read(pid, ctx.Rsp + 8 * i, 8) or b"\0" * 8)).value for i in range(96)])
                        if a.exec or a.value:
                            REGLOG.append({k: getattr(ctx, k) for k in ("Rax", "Rbx", "Rcx", "Rdx", "Rsi", "Rdi",
                                                                         "R12", "R13", "R14", "R15", "Rsp", "Rbp", "Rip")})
                            REGLOG[-1]["mem_rbx"] = (winproc_read(pid, ctx.Rbx, 0x60) or b"").hex()
                            REGLOG[-1]["mem_r13"] = (winproc_read(pid, ctx.R13, 0x8) or b"").hex()
                            REGLOG[-1]["mem_rdi"] = (winproc_read(pid, ctx.Rdi, 0x60) or b"").hex()
                            REGLOG[-1]["mem_rsi"] = (winproc_read(pid, ctx.Rsi, 0x60) or b"").hex()
                            p28 = winproc_read(pid, ctx.Rdi + 0x28, 8)
                            if p28:
                                REGLOG[-1]["mem_rdi28"] = (winproc_read(pid, int.from_bytes(p28, "little"), 0x40) or b"").hex()
                            t7 = winproc_read(pid, ctx.R15 + 0x1040, 8)
                            if t7:
                                ptr = int.from_bytes(t7, "little")
                                REGLOG[-1]["tab7"] = hex(ptr)
                                REGLOG[-1]["tab7_mem"] = (winproc_read(pid, ptr, 0x100) or b"").hex() if ptr else ""
                            REGLOG[-1]["mem_rsi"] = (winproc_read(pid, ctx.Rsi, 0x40) or b"").hex()
                            REGLOG[-1]["mem_rsp"] = (winproc_read(pid, ctx.Rsp, 0x60) or b"").hex()
                            REGLOG[-1]["mem_r14"] = (winproc_read(pid, ctx.R14, 0x60) or b"").hex()
                            REGLOG[-1]["mem_rdi"] = (winproc_read(pid, ctx.Rdi, 0x60) or b"").hex()
                            REGLOG[-1]["mem_rsi"] = (winproc_read(pid, ctx.Rsi, 0x60) or b"").hex()
                            for spec in a.dump or []:       # --dump R8:80 -> memory at that register
                                reg, _, n = spec.partition(":")
                                val = getattr(ctx, reg)
                                REGLOG[-1][reg] = val
                                REGLOG[-1]["dump_" + reg] = (winproc_read(pid, val, int(n or "40", 16)) or b"").hex()
                            if a.exec:
                                ctx.EFlags |= 0x10000  # RF: do not re-trap on the same instruction
                        ctx.Dr6 = 0
                        k32.SetThreadContext(h, ctypes.byref(ctx))
                    else:
                        status = DBG_EXCEPTION_NOT_HANDLED
                elif rec.ExceptionCode == EXCEPTION_BREAKPOINT and not armed_all:
                    # the attach breakpoint: arm every existing thread now
                    for tid in threads_of(pid):
                        if tid not in handles:
                            h = k32.OpenThread(THREAD_ALL, False, tid)
                            if h:
                                arm(tid, h)
                    armed_all = True
                else:
                    status = DBG_EXCEPTION_NOT_HANDLED
            elif code == EXIT_PROCESS_DEBUG_EVENT:
                print("process exited"); break
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
    finally:
        # Detach race (crashed the game once): a thread can already be inside a data-breakpoint
        # trap when the registers are cleared, and if we stop debugging then, its single-step
        # exception lands in shadPS4's handler as "Unhandled Exception 0x80000004". So: suspend
        # everything, clear, then keep draining events (swallowing our single-steps) before stopping.
        for h in handles.values():
            k32.SuspendThread(h)
        for h in handles.values():
            set_dr(h, 0, a.len, rw)
        for h in handles.values():
            k32.ResumeThread(h)
        quiet_until = time.time() + 1.5
        while time.time() < quiet_until:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 50):
                continue
            st = DBG_CONTINUE
            if ev.dwDebugEventCode == EXCEPTION_DEBUG_EVENT:
                c = ev.u.Exception.ExceptionRecord.ExceptionCode
                if c == EXCEPTION_SINGLE_STEP:
                    h = handles.get(ev.dwThreadId)
                    if h:
                        set_dr(h, 0, a.len, rw)
                    quiet_until = time.time() + 1.5
                elif c != EXCEPTION_BREAKPOINT:
                    st = DBG_EXCEPTION_NOT_HANDLED
            elif ev.dwDebugEventCode == CREATE_THREAD_DEBUG_EVENT:
                h = k32.OpenThread(THREAD_ALL, False, ev.dwThreadId)
                if h:
                    handles[ev.dwThreadId] = h
                    set_dr(h, 0, a.len, rw)
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, st)
        # Verify before letting go (2026-10-10: a breakpoint survived detach on one thread and
        # killed the game when the subclass screen later ran that code). Check EVERY thread of the
        # process, not only the ones we remember arming, and retry until Dr7 reads clean.
        for attempt in range(5):
            dirty = []
            for tid in threads_of(pid):
                h = handles.get(tid) or k32.OpenThread(THREAD_ALL, False, tid)
                if not h:
                    continue
                handles[tid] = h
                keep, ctx = aligned_context()
                ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS
                if k32.GetThreadContext(h, ctypes.byref(ctx)) and (ctx.Dr7 & 0xFF or ctx.Dr0):
                    k32.SuspendThread(h)
                    set_dr(h, 0, a.len, rw)
                    k32.ResumeThread(h)
                    dirty.append(tid)
            if not dirty:
                break
            print(f"== detach: cleared a leftover breakpoint on {len(dirty)} thread(s), re-checking")
        else:
            print("== ⛔ detach: some thread still holds a breakpoint - the game may crash if it runs that code")
        k32.DebugActiveProcessStop(pid)
    return split, regs


_proc = {}
REGLOG = []


def winproc_read(pid, addr, n):
    p = _proc.get(pid) or _proc.setdefault(pid, winproc.WinProc(pid))
    try:
        return p.read(addr, n)
    except Exception:
        return None


if __name__ == "__main__":
    a_all = "--stacks" in sys.argv
    if a_all:
        sys.argv.remove("--stacks")
    split, regs = main()
    exe_lo = None
    try:
        from d1guest_win import d1guest
        import argparse as _ap
        import contextlib, io
        ns = _ap.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                           no_cache=False, allow_dead=True, account_soid=None, require=0)
        with contextlib.redirect_stdout(io.StringIO()):
            _, _, _, g = d1guest.open_guest(ns)
        exe_lo = g.base
    except Exception as e:
        print("base unknown:", e)

    def fmt(x):
        return f"{x - exe_lo:#x}" if exe_lo and exe_lo <= x < exe_lo + 0x3000000 else f"host {x:#x}"
    for phase in ("before", "after"):
        print(f"== {phase}: {sum(split[phase].values())} hits, {len(split[phase])} sites")
        for rip, n in split[phase].most_common(40):
            new = " NEW" if phase == "after" and rip not in split["before"] else ""
            print(f"  {fmt(rip):>14} x{n}{new}")
    if REGLOG:
        import json as _j
        out = os.path.join(os.environ.get("TEMP", "."), "hwwatch_regs.json")
        _j.dump(REGLOG, open(out, "w"))
        print(f"== {len(REGLOG)} register snapshots -> {out}")
    print("== stack of first hit per NEW site (eboot return addresses)")
    for rip in regs:
        if a_all is False and (rip in split["before"] or rip not in split["after"]):
            continue
        rsp, stack = regs[rip]
        rets = [fmt(v) for v in stack if exe_lo and exe_lo <= v < exe_lo + 0x1900000]
        print(f"  {fmt(rip)}: {rets[:12]}")

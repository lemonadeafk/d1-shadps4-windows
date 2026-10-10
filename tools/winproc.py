"""Windows process access for d1guest - the stand-in for /proc/<pid>/{mem,stat,smaps}.

Same interface as d1guest.Proc (read / write / alive / require_alive / regions / find), built on
ReadProcessMemory, WriteProcessMemory and VirtualQueryEx. shadPS4 maps guest memory at the same
virtual addresses in its own process on Windows, so a guest address is a host address here too.

Adds suspend()/resume() (NtSuspendProcess / NtResumeProcess) for the freeze-write-thaw sequence
GUARDIAN-IN-WORLD.md requires for multi-byte hook writes (Linux does it with kill -STOP / -CONT).
"""

import ctypes
import os
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_SUSPEND_RESUME = 0x0800
STILL_ACTIVE = 259
TH32CS_SNAPPROCESS = 0x2

MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
PAGE_EXECUTE_READWRITE = 0x40
EXECUTE_FLAGS = 0x10 | 0x20 | 0x40 | 0x80   # EXECUTE, _READ, _READWRITE, _WRITECOPY
READ_FLAGS = 0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80

USER_MAX = 0x7FFF_FFFF_0000
SCAN_CHUNK = 64 * 1024 * 1024
# shadPS4 on Windows maps ALL guest physical memory a second time as one view of its backing file
# (address_space.cpp: BackingSize = ORBIS_KERNEL_TOTAL_MEM_DEV_PRO 7936 MiB + FLEXIBLE 512 MiB,
# plus config extra_dmem/extra_fmem). Every guest byte therefore appears twice, and an anchor scan
# agrees on two bases. Only the guest mapping holds the addresses the game's own pointers use, so
# the mirror is excluded from scans. Measured 2026-10-10: allocation 0x10000000000, 8448 MiB.
BACKING_SIZE = (7936 + 512 + int(os.environ.get("D1_SHADPS4_EXTRA_MEM_MB", "0"))) * 1024 * 1024


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                               ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
k32.VirtualProtectEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD,
                                 ctypes.POINTER(wintypes.DWORD)]
k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
k32.FlushInstructionCache.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]


def emu_pids(name="shadps4.exe"):
    """PIDs of running shadPS4 instances (the Linux version greps for `shadps4 -p`)."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    pids = []
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        if entry.szExeFile.lower() == name:
            pids.append(entry.th32ProcessID)
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return pids


class Dead(RuntimeError):
    """Replaced by d1guest.Dead when loaded through d1guest_win, so `except Dead` matches."""


class WinProc:
    Dead = Dead

    def __init__(self, pid):
        self.pid = pid
        access = (PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
                  | PROCESS_QUERY_INFORMATION | PROCESS_SUSPEND_RESUME)
        self.h = k32.OpenProcess(access, False, pid)
        if not self.h:
            raise SystemExit(f"OpenProcess({pid}) failed: error {ctypes.get_last_error()}")
        self.starttime = self._starttime()

    # -- liveness -----------------------------------------------------------------------------
    def _starttime(self):
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        if not k32.GetProcessTimes(self.h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return (c.dwHighDateTime << 32) | c.dwLowDateTime

    def alive(self):
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(self.h, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE and self._starttime() == self.starttime

    def require_alive(self, what):
        if not self.alive():
            raise self.Dead(f"the client died during {what} - this is an ERROR, not a zero")

    # -- memory -------------------------------------------------------------------------------
    def read(self, addr, n):
        self.require_alive("a read")
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
        if not ok or got.value != n:
            self.require_alive("a read")
            raise self.Dead(f"short read at {addr:#x}: wanted {n}, got {got.value} "
                            f"(error {ctypes.get_last_error()})")
        return buf.raw

    def write(self, addr, data):
        self.require_alive("a write")
        n = len(data)
        done = ctypes.c_size_t(0)
        if k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, n, ctypes.byref(done)) and done.value == n:
            return n
        # Guest code pages are mapped execute/read-only; open them for the write, then restore.
        old = wintypes.DWORD()
        if not k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), n, PAGE_EXECUTE_READWRITE, ctypes.byref(old)):
            raise OSError(f"VirtualProtectEx at {addr:#x} failed: error {ctypes.get_last_error()}")
        try:
            if not k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, n, ctypes.byref(done)) \
                    or done.value != n:
                raise OSError(f"WriteProcessMemory at {addr:#x} failed: error {ctypes.get_last_error()}")
        finally:
            tmp = wintypes.DWORD()
            k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), n, old.value, ctypes.byref(tmp))
        k32.FlushInstructionCache(self.h, ctypes.c_void_p(addr), n)
        return n

    # -- freeze / thaw ------------------------------------------------------------------------
    def suspend(self):
        status = ntdll.NtSuspendProcess(self.h)
        if status != 0:
            raise OSError(f"NtSuspendProcess failed: NTSTATUS {status & 0xFFFFFFFF:#x}")

    def resume(self):
        status = ntdll.NtResumeProcess(self.h)
        if status != 0:
            raise OSError(f"NtResumeProcess failed: NTSTATUS {status & 0xFFFFFFFF:#x}")

    # -- mappings -----------------------------------------------------------------------------
    def regions(self, executable_only=False):
        """Committed, readable regions (the analogue of smaps' Rss > 0 filter).

        Like the Linux version, never filter by size: shadPS4 reserves huge ranges and the guest
        heap lives inside them. Only COMMITTED pages are listed, so reserved space costs nothing.
        """
        out, addr = [], 0
        alloc_total = {}
        mbi = MEMORY_BASIC_INFORMATION()
        while addr < USER_MAX:
            if not k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            alloc = mbi.AllocationBase or 0
            if alloc:
                alloc_total[alloc] = alloc_total.get(alloc, 0) + size
            prot = mbi.Protect
            if (mbi.State == MEM_COMMIT and prot & READ_FLAGS and not prot & (PAGE_GUARD | PAGE_NOACCESS)
                    and (not executable_only or prot & EXECUTE_FLAGS)):
                out.append((base, base + size, f"{prot:#x}", alloc))
            addr = base + size
        mirrors = {a for a, total in alloc_total.items() if total == BACKING_SIZE}
        self.excluded_mirrors = sorted(mirrors)
        return [(lo, hi, perm) for lo, hi, perm, alloc in out if alloc not in mirrors]

    def find(self, sig, executable_only=False, limit=16):
        hits, scanned = [], 0
        overlap = len(sig) - 1
        for lo, hi, _perm in self.regions(executable_only):
            pos = lo
            while pos < hi:
                n = min(SCAN_CHUNK, hi - pos)
                buf = ctypes.create_string_buffer(n)
                got = ctypes.c_size_t(0)
                k32.ReadProcessMemory(self.h, ctypes.c_void_p(pos), buf, n, ctypes.byref(got))
                blob = buf.raw[:got.value]
                scanned += len(blob)
                start = 0
                while True:
                    j = blob.find(sig, start)
                    if j < 0:
                        break
                    if pos + j not in hits:
                        hits.append(pos + j)
                    start = j + 1
                    if len(hits) >= limit:
                        return hits, scanned
                if not blob or pos + n >= hi:
                    break
                pos += n - overlap
        return hits, scanned

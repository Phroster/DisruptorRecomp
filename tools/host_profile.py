#!/usr/bin/env python3
"""Host-side sampling profiler for the running game (no rebuild needed).

Usage: python tools/host_profile.py --exe build-fast/DisruptorRecompiled.exe
                                    [--seconds 8] [--top 30] [--hz 1000]

Picks the game's busiest thread, samples its instruction pointer
(SuspendThread / GetThreadContext), and resolves the samples against the exe's
own symbol table (nm). Samples that land in another module are counted per
module. Answers "where does the host CPU go" - recompiled game code, the
runtime's timing helpers, the GPU rasteriser, the SPU - which the guest-side
function histogram cannot.
"""
import bisect
import collections
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
TH32CS_SNAPTHREAD, TH32CS_SNAPMODULE, TH32CS_SNAPPROCESS = 0x4, 0x8, 0x2
THREAD_ACCESS = 0x0002 | 0x0008 | 0x0040  # SUSPEND_RESUME | GET_CONTEXT | QUERY_INFORMATION
CONTEXT_CONTROL = 0x100001


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", wt.LONG),
                ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", wt.LONG), ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
                ("hModule", wt.HMODULE), ("szModule", ctypes.c_char * 256),
                ("szExePath", ctypes.c_char * 260)]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE
k32.OpenThread.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.GetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
k32.SuspendThread.argtypes = [wt.HANDLE]
k32.ResumeThread.argtypes = [wt.HANDLE]
k32.GetThreadTimes.argtypes = [wt.HANDLE] + [ctypes.c_void_p] * 4


def find_pid(name):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    e = PROCESSENTRY32()
    e.dwSize = ctypes.sizeof(e)
    ok = k32.Process32First(snap, ctypes.byref(e))
    pid = None
    while ok:
        if e.szExeFile.decode(errors="replace").lower() == name.lower():
            pid = e.th32ProcessID
        ok = k32.Process32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return pid


def modules(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | 0x10, pid)
    e = MODULEENTRY32()
    e.dwSize = ctypes.sizeof(e)
    out = []
    ok = k32.Module32First(snap, ctypes.byref(e))
    while ok:
        out.append((e.modBaseAddr, e.modBaseSize, e.szModule.decode(errors="replace")))
        ok = k32.Module32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    e = THREADENTRY32()
    e.dwSize = ctypes.sizeof(e)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(e))
    while ok:
        if e.th32OwnerProcessID == pid:
            out.append(e.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def cpu_time(h):
    ft = [ctypes.c_ulonglong() for _ in range(4)]
    k32.GetThreadTimes(h, *[ctypes.byref(x) for x in ft])
    return ft[2].value + ft[3].value


def main():
    a = sys.argv[1:]
    exe = a[a.index("--exe") + 1] if "--exe" in a else "build/DisruptorRecompiled.exe"
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 8.0
    top = int(a[a.index("--top") + 1]) if "--top" in a else 30
    hz = float(a[a.index("--hz") + 1]) if "--hz" in a else 1000.0

    syms = []
    for line in subprocess.run(["nm", "-n", exe], capture_output=True, text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 3 and p[1] in "TtWw":
            syms.append((int(p[0], 16), p[2]))
    syms.sort()
    addrs = [s[0] for s in syms]
    image_base = 0x140000000

    pid = find_pid(os.path.basename(exe))
    if pid is None:
        sys.exit("game is not running")
    mods = modules(pid)
    exe_mod = next(m for m in mods if m[2].lower() == os.path.basename(exe).lower())

    handles = {t: k32.OpenThread(THREAD_ACCESS, False, t) for t in threads(pid)}
    before = {t: cpu_time(h) for t, h in handles.items() if h}
    time.sleep(1.0)
    busiest = max(before, key=lambda t: cpu_time(handles[t]) - before[t])
    h = handles[busiest]

    ctx = (ctypes.c_ubyte * 1232)()
    # CONTEXT must be 16-byte aligned; ctypes arrays from the heap are.
    ctypes.cast(ctx, ctypes.POINTER(ctypes.c_uint32))[0x30 // 4] = CONTEXT_CONTROL
    rip_at = ctypes.cast(ctypes.addressof(ctx) + 0xF8, ctypes.POINTER(ctypes.c_uint64))
    hits = collections.Counter()
    n = 0
    end = time.perf_counter() + secs
    while time.perf_counter() < end:
        if k32.SuspendThread(h) != 0xFFFFFFFF:
            ok = k32.GetThreadContext(h, ctx)
            k32.ResumeThread(h)
            if ok:
                rip = rip_at[0]
                n += 1
                if exe_mod[0] <= rip < exe_mod[0] + exe_mod[1]:
                    i = bisect.bisect_right(addrs, rip - exe_mod[0] + image_base) - 1
                    hits[syms[i][1] if i >= 0 else "?"] += 1
                else:
                    m = next((m[2] for m in mods if m[0] <= rip < m[0] + m[1]), "<other>")
                    hits["[" + m + "]"] += 1
        time.sleep(1.0 / hz)
    print("thread %d, %d samples" % (busiest, n))
    for name, c in hits.most_common(top):
        print("%6.2f%%  %s" % (100.0 * c / max(1, n), name))


if __name__ == "__main__":
    main()

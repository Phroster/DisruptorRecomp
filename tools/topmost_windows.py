#!/usr/bin/env python3
"""List visible top-level windows that sit above normal windows (topmost and/or
layered). One of these covering the game keeps Windows compositing the desktop,
which stops a borderless game from getting independent flip and G-SYNC/VRR.

Usage: python tools/topmost_windows.py
"""
import ctypes
import ctypes.wintypes as wt

u32 = ctypes.WinDLL("user32")
k32 = ctypes.WinDLL("kernel32")
psapi = ctypes.WinDLL("psapi")
WS_EX_TOPMOST, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOREDIRECTIONBITMAP = 0x8, 0x80000, 0x20, 0x200000
k32.OpenProcess.restype = wt.HANDLE


def proc_name(pid):
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return "?"
    buf = ctypes.create_unicode_buffer(520)
    n = wt.DWORD(520)
    ok = k32.QueryFullProcessImageNameW(wt.HANDLE(h), 0, buf, ctypes.byref(n))
    k32.CloseHandle(wt.HANDLE(h))
    return buf.value.rsplit("\\", 1)[-1] if ok else "?"


rows = []


@ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def cb(hwnd, _):
    if not u32.IsWindowVisible(hwnd):
        return True
    ex = u32.GetWindowLongW(hwnd, -20)
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 50 or h < 50:
        return True
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = ctypes.create_unicode_buffer(128)
    u32.GetWindowTextW(hwnd, title, 128)
    flags = [n for n, b in (("TOPMOST", WS_EX_TOPMOST), ("LAYERED", WS_EX_LAYERED),
                            ("CLICKTHROUGH", WS_EX_TRANSPARENT)) if ex & b]
    rows.append((proc_name(pid.value), "%dx%d@%d,%d" % (w, h, r.left, r.top), " ".join(flags), title.value))
    return True


u32.EnumWindows(cb, 0)
print("z-order top to bottom:")
for i, row in enumerate(rows[:25]):
    print("%2d  %-28s %-22s %-28s %s" % ((i,) + row))

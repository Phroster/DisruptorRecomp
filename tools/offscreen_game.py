#!/usr/bin/env python3
"""Start the diagnostics build with its real GL renderer, but out of the way:
no sound (SDL dummy audio driver), window moved off every monitor as soon as it
exists, keyboard focus handed back to the window that had it.

Usage: python tools/offscreen_game.py [--dir build] [--overclock 300]
Prints the pid and returns once the window is parked. The caller talks to the
debug port and kills the pid when done. Needed because the precise-vertex
(PGXP) lookups and the supersampled picture only exist on the GL path; the
headless frontend has neither.
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

u32 = ctypes.WinDLL("user32")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10


def windows_of(pid):
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return found


def main():
    a = sys.argv[1:]
    d = a[a.index("--dir") + 1] if "--dir" in a else "build"
    oc = a[a.index("--overclock") + 1] if "--overclock" in a else "300"
    env = dict(os.environ)
    for k in ("PSX_HEADLESS", "PSX_HEADLESS_INPUT"):
        env.pop(k, None)
    env.update({"SDL_AUDIO_DRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
                "PSX_OVERLAY_AUTOCOMPILE_OFF": "1", "PSX_CPU_OVERCLOCK": oc,
                "PSX_GL_DXGI": "0"})
    # Match the play launcher's presentation defaults when measuring the GL path.
    for key, value in {"PSX_GL_SMART_FILTER": "1", "PSX_GL_CRACK_FILL": "0.45",
                       "PSX_GL_TILE_BLEND": "1.0", "PSX_GL_FMV_CONTENT": "320x180",
                       "PSX_GL_FMV_FILTER": "bicubic"}.items():
        env.setdefault(key, value)
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    out = open(os.path.join(ROOT, "logs", "offscreen.out"), "wb")
    err = open(os.path.join(ROOT, "logs", "offscreen.err"), "wb")
    before = u32.GetForegroundWindow()
    proc = subprocess.Popen([os.path.join(ROOT, d, "DisruptorRecompiled.exe"),
                             "--game", "game.toml", "--disc", "disc/Disruptor.cue"],
                            cwd=ROOT, env=env, stdout=out, stderr=err,
                            creationflags=0x08000000)  # CREATE_NO_WINDOW (no console)
    parked = False
    end = time.time() + 20
    while time.time() < end:
        for hwnd in windows_of(proc.pid):
            u32.SetWindowPos(hwnd, 0, -30000, -30000, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            parked = True
        if parked:
            break
        time.sleep(0.005)
    if before:
        u32.SetForegroundWindow(before)
    # Keep it parked: the runtime may re-centre the window once at startup.
    for _ in range(100):
        for hwnd in windows_of(proc.pid):
            r = wt.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.left > -20000:
                u32.SetWindowPos(hwnd, 0, -30000, -30000, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                if before:
                    u32.SetForegroundWindow(before)
        time.sleep(0.02)
    print("pid %d parked=%s" % (proc.pid, parked))


if __name__ == "__main__":
    main()

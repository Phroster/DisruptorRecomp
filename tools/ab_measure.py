#!/usr/bin/env python3
"""Sequential A/B: launch headless, load slot 3, verify gameplay, measure
polygons/s wall and yaw turn/s wall. Usage: ab_measure.py <port> [vblank_div]"""
import os
import subprocess
import sys
import time

from input_probe import send

PORT = int(sys.argv[1])
DIV = sys.argv[2] if len(sys.argv) > 2 else ""
YAW = 0x80077624
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gpu_polys(port):
    r = send(port, '{"cmd":"gpu_opcodes"}')
    return sum(v for k, v in r.get("opcodes", {}).items()
               if 0x20 <= int(k, 16) <= 0x7F)


def yaw(port):
    return int(send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)["hex"], 16)


def main():
    env = ("set PSX_HEADLESS=1 && set PSX_HEADLESS_INPUT=1 && set PSX_BIOS_HLE=1 && "
           "set PSX_RUNTIME_PERF_DIAG=1 && set PSX_RUNTIME_PERF_DIAG_MS=2000 && ")
    if DIV:
        env += "set PSX_VBLANK_DIV=%s && " % DIV
    log = "logs\\ab_%s.out" % (DIV or "base")
    cmd = ('cmd.exe /c cd /d "%s" && %s"build\\DisruptorRecompiled.exe" '
           '--game game.toml --disc disc/Disruptor.cue --debug-port %d > "%s" 2>&1'
           % (ROOT, env, PORT, log))
    subprocess.Popen(cmd, shell=False)
    time.sleep(12)
    send(PORT, '{"cmd":"savestate","op":"load","slot":3}')
    time.sleep(4)

    send(PORT, '{"cmd":"set_input","buttons":65503}')
    time.sleep(0.4)
    y0 = yaw(PORT)
    time.sleep(0.5)
    y1 = yaw(PORT)
    if y0 == y1:
        print("WARNING: yaw not changing - not in gameplay?")

    p0 = gpu_polys(PORT)
    y_prev = yaw(PORT)
    changes = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 6.0:
        y = yaw(PORT)
        if y != y_prev:
            changes += 1
            y_prev = y
    dt = time.perf_counter() - t0
    p1 = gpu_polys(PORT)
    send(PORT, '{"cmd":"clear_input"}')
    print("div=%s port=%d: polys=%d in %.2fs -> %.0f polys/s wall | yaw %d changes -> %.1f/s wall"
          % (DIV or "1", PORT, p1 - p0, dt, (p1 - p0) / dt, changes, changes / dt))


if __name__ == "__main__":
    main()

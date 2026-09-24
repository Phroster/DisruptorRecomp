#!/usr/bin/env python3
"""Rendering vs logic rate in guest time: polygon opcode counts and turn-rate
yaw changes, normalized by the PSX timer counters (guest cycles)."""
import json
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4626
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
YAW = 0x80077624
CYCLES_PER_SEC = 33868800.0


def gpu_polys(port):
    r = send(port, '{"cmd":"gpu_opcodes"}')
    ops = r.get("opcodes", {})
    total = 0
    for k, v in ops.items():
        op = int(k, 16)
        if 0x20 <= op <= 0x7F:
            total += v
    return total


def timer0(port):
    r = send(port, '{"cmd":"timers_state"}')
    return r["timers"][0]["counter"]


def yaw(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)
    return int(r["hex"], 16)


def main():
    send(PORT, '{"cmd":"set_input","buttons":65503}')
    time.sleep(0.3)

    p0 = gpu_polys(PORT)
    t0 = timer0(PORT)
    wall0 = time.perf_counter()
    y_prev = yaw(PORT)
    yaw_changes = 0
    last = wall0
    while time.perf_counter() - wall0 < DUR:
        y = yaw(PORT)
        if y != y_prev:
            yaw_changes += 1
            y_prev = y
    wall1 = time.perf_counter()
    t1 = timer0(PORT)
    p1 = gpu_polys(PORT)
    send(PORT, '{"cmd":"clear_input"}')

    dt = wall1 - wall0
    dcyc = (t1 - t0) & 0xFFFFFFFF
    guest_sec = dcyc / CYCLES_PER_SEC
    print("port %d: wall=%.2fs guest=%.2fs (%.2fx) polys +%d -> %.0f/s guest" %
          (PORT, dt, guest_sec, guest_sec / dt, p1 - p0, (p1 - p0) / guest_sec))
    print("  yaw changes=%d -> %.1f/s guest, %.1f/s wall" %
          (yaw_changes, yaw_changes / guest_sec, yaw_changes / dt))


if __name__ == "__main__":
    main()

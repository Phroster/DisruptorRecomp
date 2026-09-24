#!/usr/bin/env python3
"""Guest-time normalized rates: draw frames/s and turn/s per GUEST second.
Usage: guest_norm.py <port> <vblank_cycles> [dur]"""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1])
VBL = int(sys.argv[2])          # current cycles per vblank (564480 or 282240)
DUR = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
CYCLES = 33868800.0
YAW = 0x80077624


def vblanks(port):
    return send(port, '{"cmd":"vblank_rate"}')["delivered"]


def frames(port):
    return send(port, '{"cmd":"gpu_ring_stats"}')["newest_frame"]


def yaw(port):
    return int(send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)["hex"], 16)


def main():
    send(PORT, '{"cmd":"set_input","buttons":65503}')
    time.sleep(0.4)
    v0, f0 = vblanks(PORT), frames(PORT)
    y_prev = yaw(PORT)
    changes = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < DUR:
        y = yaw(PORT)
        if y != y_prev:
            changes += 1
            y_prev = y
    dt = time.perf_counter() - t0
    v1, f1 = vblanks(PORT), frames(PORT)
    send(PORT, '{"cmd":"clear_input"}')

    dv = v1 - v0
    guest_sec = dv * VBL / CYCLES
    print("port=%d dur=%.2fs vblanks +%d -> %.0f/s wall; guest=%.2fs (%.2fx)"
          % (PORT, dt, dv, dv / dt, guest_sec, guest_sec / dt))
    print("  guest frames +%d -> %.1f/s guest; draws/s guest ~%.1f (every-2nd-frame)"
          % (f1 - f0, (f1 - f0) / guest_sec, (f1 - f0) / 2 / guest_sec))
    print("  yaw changes=%d -> %.1f/s guest, %.1f/s wall"
          % (changes, changes / guest_sec, changes / dt))


if __name__ == "__main__":
    main()

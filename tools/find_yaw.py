#!/usr/bin/env python3
"""Find the player yaw variable by differential RAM analysis.

Runs three windows (turn right held, turn left held, no input), sampling full
RAM at a fixed cadence in each. A yaw counter shows a constant-rate delta with
opposite signs for the two directions and stays stable when idle.

Usage: python tools/find_yaw.py [--port 4624] [--slot 3] [--samples 5] [--dt 0.35]
"""
import argparse
import sys
import time

from input_probe import BUTTONS, load_state, read_ram, send

RIGHT = 0xFFFF & ~BUTTONS["right"]
LEFT = 0xFFFF & ~BUTTONS["left"]


def window(port, name, word, samples, dt):
    if word is not None:
        send(port, '{"cmd":"set_input","buttons":%d}' % word)
    snaps = []
    for _ in range(samples):
        snaps.append(read_ram(port))
        if dt:
            time.sleep(dt)
    if word is not None:
        send(port, '{"cmd":"clear_input"}')
    print(f"  window {name}: {len(snaps)} samples, {len(snaps[0])} bytes", flush=True)
    return snaps


def deltas(snaps):
    out = []
    for a, b in zip(snaps, snaps[1:]):
        out.append([(x - y) & 0xFF for x, y in zip(b, a)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--dt", type=float, default=0.0)
    args = ap.parse_args()

    load_state(args.port, args.slot)
    print("idle window", flush=True)
    idle = window(args.port, "idle", None, args.samples, args.dt)
    load_state(args.port, args.slot)
    print("right window", flush=True)
    right = window(args.port, "right", RIGHT, args.samples, args.dt)
    load_state(args.port, args.slot)
    print("left window", flush=True)
    left = window(args.port, "left", LEFT, args.samples, args.dt)

    idle_d = deltas(idle)
    right_d = deltas(right)
    left_d = deltas(left)

    n = len(idle[0])
    s1 = s2 = 0
    cands = []
    for addr in range(n):
        id_vals = [d[addr] for d in idle_d]
        if any(v not in (0, 1, 255) for v in id_vals):
            continue                      # idle must be stable
        s1 += 1
        r = [d[addr] for d in right_d]
        l = [d[addr] for d in left_d]
        r_nz = sum(1 for v in r if v not in (0, 255))
        l_nz = sum(1 for v in l if v not in (0, 255))
        if r_nz < max(1, len(r) - 1) or l_nz < max(1, len(l) - 1):
            continue                      # must move while turning
        s2 += 1
        rs = [1 if v < 128 else -1 for v in r if v not in (0, 255)]
        ls = [1 if v < 128 else -1 for v in l if v not in (0, 255)]
        if not rs or not ls:
            continue
        if sum(rs) * sum(ls) >= 0:
            continue                      # opposite directions required
        cands.append((addr, r, l))

    print(f"idle-stable: {s1}; turn-active: {s2}; opposite-sign: {len(cands)}")
    for addr, r, l in cands[:60]:
        print(f"  0x{addr:06X} right={r} left={l}")


if __name__ == "__main__":
    main()

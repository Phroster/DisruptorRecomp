#!/usr/bin/env python3
"""Validate yaw candidates: a yaw counter changes at a constant rate while a
turn button is held and is flat when idle.

Usage: python tools/yaw_check.py 0x0745AC 0x074658 ...
"""
import argparse
import struct
import sys
import time

from input_probe import BUTTONS, load_state, send


def word(port, addr):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":2}' % addr)
    return struct.unpack("<H", bytes.fromhex(r["hex"]))[0]


def run(port, addr, word_btn, label):
    vals = []
    t0 = time.time()
    ts = []
    for _ in range(18):
        vals.append(word(port, addr))
        ts.append(time.time() - t0)
    deltas = []
    for i in range(1, len(vals)):
        dt = ts[i] - ts[i - 1]
        d = (vals[i] - vals[i - 1]) & 0xFFFF
        if d > 32768:
            d -= 65536
        deltas.append(round(d / dt, 1) if dt > 0 else 0)
    print(f"  {label}: vals={vals}")
    print(f"      deltas/s={deltas}")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addrs", nargs="+")
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    args = ap.parse_args()
    addrs = [int(a, 0) for a in args.addrs]
    load_state(args.port, args.slot)
    for addr in addrs:
        send(args.port, '{"cmd":"clear_input"}')
        time.sleep(0.3)
        run(args.port, addr, None, f"0x{addr:06X} idle")
        send(args.port, '{"cmd":"set_input","buttons":%d}' % (0xFFFF & ~BUTTONS["right"]))
        time.sleep(0.2)
        run(args.port, addr, "right", f"0x{addr:06X} turning")
        send(args.port, '{"cmd":"clear_input"}')
        time.sleep(0.3)


if __name__ == "__main__":
    main()

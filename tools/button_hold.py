#!/usr/bin/env python3
"""Held-button probe: distinguishes continuous movement from one-shot actions.

Loads the state, holds a button via set_input, and samples the camera window
(scratch 0x40..0x4F) plus ammo at ~0.3 s / 0.8 s / 1.3 s. Growing deltas mean
continuous motion (strafe/turn); a single step means a discrete action
(weapon switch, toggle).

Usage: python tools/button_hold.py --only l1,r1,l2,r2 [--slot 3]
"""
import argparse
import sys
import time

from input_probe import BUTTONS, load_state, send

AMMO = 0x056A94


def scratch(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x1F800040","len":16}')
    return bytes.fromhex(r["hex"])


def ammo(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % AMMO)
    return int(r["hex"], 16)


def run(port, name, slot):
    word = 0xFFFF & ~BUTTONS[name]
    load_state(port, slot)
    base = scratch(port)
    a0 = ammo(port)
    send(port, '{"cmd":"set_input","buttons":%d}' % word)
    samples = []
    for delay in (0.3, 0.5, 0.5):
        time.sleep(delay)
        samples.append((scratch(port), ammo(port)))
    send(port, '{"cmd":"clear_input"}')
    print(f"== {name} word=0x{word:04X} ammo {a0:#04x} -> "
          f"{[f'{a:#04x}' for _, a in samples]}")
    for i, (s, _) in enumerate(samples):
        d = tuple(x - y for x, y in zip(s, base))
        print(f"   t={0.3 + 0.5 * i:.1f}s scratch40={d}")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    ap.add_argument("--only", default="l1,r1,l2,r2")
    args = ap.parse_args()
    for name in args.only.split(","):
        if name not in BUTTONS:
            print("unknown:", name)
            continue
        try:
            run(args.port, name, args.slot)
        except Exception as exc:
            print("ERR", name, exc)


if __name__ == "__main__":
    main()

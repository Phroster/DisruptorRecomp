#!/usr/bin/env python3
"""Classify what each PSX button does, using anchors found by RAM diffing.

Anchors (Disruptor, from tools/input_probe.py):
  0x056A94  current-weapon ammo counter   (Cross fire: 0x39 -> 0x38)
  0x077668  psi energy                    (Square psionic: 0x28 -> 0x23)
  0x1F8000  scratch camera window (0x40..0x4F moves with the player)

For each button: load the state, sample the anchors at rest, press 4 frames,
sample at +0.15 s (mid-action) and +0.9 s (settled), three repetitions.
Prints a compact row per button so the function can be read off.

Usage: python tools/button_classify.py [--port 4624] [--slot 3] [--only a,b]
"""
import argparse
import sys
import time

from input_probe import BUTTONS, load_state, send

AMMO = 0x056A94
PSI = 0x077668


def byte(port, addr):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % addr)
    return int(r["hex"], 16)


def scratch(port, addr, n):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":%d}' % (addr, n))
    return bytes.fromhex(r["hex"])


def snap(port):
    return (byte(port, AMMO), byte(port, PSI), scratch(port, 0x1F800040, 16))


def run_button(port, name, slot):
    word = 0xFFFF & ~BUTTONS[name]
    rows = []
    for rep in range(3):
        load_state(port, slot)
        a0 = snap(port)
        send(port, '{"cmd":"press","buttons":%d,"frames":4}' % word)
        time.sleep(0.15)
        a1 = snap(port)
        time.sleep(0.75)
        a2 = snap(port)
        rows.append((a0, a1, a2))
    print(f"== {name}  word=0x{word:04X}")
    for rep, (a0, a1, a2) in enumerate(rows):
        d_mid = tuple(x - y for x, y in zip(a1[2], a0[2]))
        d_end = tuple(x - y for x, y in zip(a2[2], a0[2]))
        print(f"  rep{rep}: ammo {a0[0]:#04x}->{a1[0]:#04x}->{a2[0]:#04x}  "
              f"psi {a0[1]:#04x}->{a1[1]:#04x}->{a2[1]:#04x}")
        print(f"         scratch40 mid={d_mid} end={d_end}")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    names = args.only.split(",") if args.only else list(BUTTONS)
    for name in names:
        if name not in BUTTONS:
            print("unknown:", name)
            continue
        try:
            run_button(args.port, name, args.slot)
        except Exception as exc:
            print("ERR", name, exc)


if __name__ == "__main__":
    main()

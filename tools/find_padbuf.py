#!/usr/bin/env python3
"""Locate the game's pad-state buffer by value search, then trace its readers.

Holds Right and scans RAM for the active-low pad word (0xFFDF); releases and
scans again (0xFFFF). An address that toggles with the button is the pad
buffer. Prints candidates and (if found) the newest read-trace PCs.

Usage: python tools/find_padbuf.py [--port 4624] [--slot 3]
"""
import argparse
import struct
import sys
import time

from input_probe import BUTTONS, load_state, read_ram, send

WANT = {0xFFDF, 0xFF9F, 0xFF7F, 0xFFFB, 0xFFEF}


def words(ram):
    return struct.unpack_from("<%dH" % (len(ram) // 2), ram, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    args = ap.parse_args()

    load_state(args.port, args.slot)
    send(args.port, '{"cmd":"set_input","buttons":%d}' % (0xFFFF & ~BUTTONS["right"]))
    time.sleep(0.4)
    held = words(read_ram(args.port))
    send(args.port, '{"cmd":"clear_input"}')
    time.sleep(0.4)
    idle = words(read_ram(args.port))

    cands = []
    for i, v in enumerate(held):
        if v in WANT and idle[i] == 0xFFFF:
            cands.append((i * 2, v))
    print(f"pad-word candidates (held != idle==FFFF): {len(cands)}")
    for a, v in cands[:20]:
        print(f"  0x{a:06X} held={v:#06x}")
    if not cands:
        return
    a = cands[0][0]
    send(args.port, '{"cmd":"rtrace_arm","lo":"0x%X","hi":"0x%X"}' % (a, a + 4))
    time.sleep(1.5)
    r = send(args.port, '{"cmd":"rtrace_dump","newest":1,"count":10}')
    seen = []
    for e in r.get("entries", []):
        key = (e["pc"], e["ra"])
        if key not in seen:
            seen.append(key)
    print(f"readers of 0x{a:06X}:")
    for pc, ra in seen:
        print(f"  pc={pc} ra={ra}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

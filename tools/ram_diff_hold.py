#!/usr/bin/env python3
"""RAM bytes that change when a second button is added to a held one.

Usage: python tools/ram_diff_hold.py --base l1 --add down [--reps 3]   (state loaded)
Holds --base, reads RAM twice (drift), adds --add briefly, releases it, reads
RAM again; prints bytes that changed in every repetition but not in drift.
Also prints the game's selection words.
"""
import json
import struct
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624


def q(**k):
    return ask(PORT, json.dumps(k), timeout=30.0, tries=2)


def ram():
    r = q(cmd="read_ram", addr="0x80000000", len=0x200000)
    return bytes.fromhex(r.get("hex") or r.get("data") or "")


def main():
    a = sys.argv[1:]
    base = a[a.index("--base") + 1]
    add = a[a.index("--add") + 1]
    reps = int(a[a.index("--reps") + 1]) if "--reps" in a else 3
    bm = 0xFFFF & ~BUTTONS[base]
    am = bm & ~BUTTONS[add]
    q(cmd="set_input", buttons=bm)
    time.sleep(0.4)
    common = None
    for r in range(reps):
        r0 = ram()
        time.sleep(0.15)
        r1 = ram()
        drift = {i for i in range(len(r0)) if r0[i] != r1[i]}
        q(cmd="set_input", buttons=am)
        time.sleep(0.12)
        q(cmd="set_input", buttons=bm)
        time.sleep(0.15)
        r2 = ram()
        ch = {i for i in range(len(r1)) if r1[i] != r2[i]} - drift
        common = ch if common is None else common & ch
        m = r2
        print("rep %d: changed %d, 0x77627.. = %s, 0x77678 = %08X" % (
            r, len(ch), m[0x77627:0x7762B].hex(), struct.unpack_from("<I", m, 0x77678)[0]))
    q(cmd="clear_input")
    print("changed in every repetition:", ["0x%06X" % i for i in sorted(common)[:40]])


if __name__ == "__main__":
    main()

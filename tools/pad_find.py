#!/usr/bin/env python3
"""Find where the game keeps the pad state, and the code that reads it.

Usage: python tools/pad_find.py [--buttons l1,r1,square]   (state already loaded)

For each button: RAM with the button held (set_input) against RAM idle, twice.
A 16-bit word that differs by exactly that button's bit, in either polarity and
either byte order, in both repetitions, is pad state. The newest readers of each
candidate are listed from the read trace (pc, ra).
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


def words(b):
    return struct.unpack_from("<%dH" % (len(b) // 2), b, 0)


def main():
    a = sys.argv[1:]
    names = (a[a.index("--buttons") + 1] if "--buttons" in a else "l1,r1,square").split(",")
    found = {}
    for name in names:
        bit = BUTTONS[name]
        hits = None
        for _ in range(2):
            q(cmd="clear_input")
            time.sleep(0.3)
            idle = words(ram())
            q(cmd="set_input", buttons=0xFFFF & ~bit)
            time.sleep(0.3)
            held = words(ram())
            q(cmd="clear_input")
            cur = set()
            swapped = ((bit & 0xFF) << 8) | (bit >> 8)
            for i, (x, y) in enumerate(zip(idle, held)):
                if (x ^ y) in (bit, swapped):
                    cur.add(i * 2)
            hits = cur if hits is None else hits & cur
        found[name] = sorted(hits)
        print("%-7s pad-state candidates: %s" % (
            name, ["0x%06X" % h for h in found[name][:16]]))
    common = sorted(set.intersection(*[set(v) for v in found.values()])) if found else []
    print("common to all buttons:", ["0x%06X" % h for h in common[:16]])
    for addr in common[:6]:
        q(cmd="rtrace_clear")
        q(cmd="rtrace_arm", lo="0x%X" % addr, hi="0x%X" % (addr + 2))
        q(cmd="set_input", buttons=0xFFFF & ~BUTTONS[names[0]])
        time.sleep(1.0)
        q(cmd="clear_input")
        time.sleep(0.3)
        r = q(cmd="rtrace_dump", newest=1, count=400)
        seen = {}
        for e in r.get("entries", []):
            key = (e.get("pc"), e.get("ra"))
            seen[key] = seen.get(key, 0) + 1
        print("readers of 0x%06X:" % addr)
        for (pc, ra), n in sorted(seen.items(), key=lambda kv: -kv[1])[:12]:
            print("    pc=%s ra=%s  x%d" % (pc, ra, n))
        q(cmd="rtrace_clear")


if __name__ == "__main__":
    main()

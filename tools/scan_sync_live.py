#!/usr/bin/env python3
"""Scan live guest RAM for jal-to-0x8004B3D4 call sites (authoritative)."""
import sys

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
WORD = 0x0C012CF5  # jal 0x8004B3D4
lo, hi = 0x80010000, 0x80070000
CH = 0x10000

outs = []
off = lo
while off < hi:
    r = send(PORT, '{"cmd":"read_ram","addr":"0x%X","len":%d}' % (off, CH))
    raw = bytes.fromhex(r["hex"])
    for i in range(0, len(raw) - 3, 4):
        if int.from_bytes(raw[i:i + 4], "little") == WORD:
            outs.append(off + i)
    off += CH
print("live sites (%d):" % len(outs))
print(" ".join("0x%08X" % a for a in outs))

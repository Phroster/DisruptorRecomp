#!/usr/bin/env python3
"""Read the game's event struct 0x8005A864: mask + 11 callbacks, plus the mask
sources 0x8005A894 / pointers at 0x8005B8F0 / 0x8005B8F4."""
import sys

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630


def rd(addr, n):
    r = send(PORT, '{"cmd":"read_ram","addr":"0x%X","len":%d}' % (addr, n))
    return bytes.fromhex(r["hex"])


base = 0x8005A864
raw = rd(base, 4 + 11 * 4 + 64)
mask = int.from_bytes(raw[0:2], "little")
print("struct 0x8005A864: mask16=0x%04X" % mask)
for i in range(11):
    v = int.from_bytes(raw[4 + i * 4:8 + i * 4], "little")
    print("  callback[%2d] = 0x%08X" % (i, v))

pend = int.from_bytes(rd(0x8005A894, 2), "little")
print("0x8005A894 (pending) = 0x%04X" % pend)

for addr in (0x8005B8F0, 0x8005B8F4):
    p = int.from_bytes(rd(addr, 4), "little")
    if 0x80000000 <= p < 0x80200000:
        v = int.from_bytes(rd(p, 2), "little")
        print("0x%08X -> 0x%08X mask=0x%04X" % (addr, p, v))
    else:
        print("0x%08X -> 0x%08X (not a pointer)" % (addr, p))

#!/usr/bin/env python3
"""Test whether runtime honors RAM code patches: nop the known submit jal at
0x800440B8 and watch polygon output collapse."""
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
ADDR = 0x800440B8
ORIG = 0x0C0134D2  # jal 0x8004D348


def polys(port):
    r = send(port, '{"cmd":"gpu_opcodes"}')
    return sum(v for k, v in r.get("opcodes", {}).items()
               if 0x20 <= int(k, 16) <= 0x7F)


def rate(port, secs=2.0):
    p0 = polys(port)
    t0 = time.perf_counter()
    time.sleep(secs)
    return (polys(port) - p0) / (time.perf_counter() - t0)


def poke(port, addr, word):
    for i in range(4):
        b = (word >> (8 * i)) & 0xFF
        r = send(port, '{"cmd":"write_ram","addr":"0x%X","val":"0x%02X"}'
                 % (addr + i, b))
        if not r.get("ok"):
            print("write failed:", r)
            return False
    return True


def peek(port, addr):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":4}' % addr)
    return int.from_bytes(bytes.fromhex(r["hex"]), "little")


print("current word at 0x%08X: 0x%08X" % (ADDR, peek(PORT, ADDR)))
print("baseline polys/s: %.0f" % rate(PORT))
print("nop-ing jal...", poke(PORT, ADDR, 0x00000000))
time.sleep(0.3)
print("word now: 0x%08X" % peek(PORT, ADDR))
print("polys/s with jal nop'd: %.0f" % rate(PORT))
print("restoring...", poke(PORT, ADDR, ORIG))
time.sleep(0.3)
print("polys/s after restore: %.0f" % rate(PORT))

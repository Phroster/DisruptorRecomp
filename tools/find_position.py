#!/usr/bin/env python3
"""Find player position: hold forward and diff RAM."""
import sys
import time

from input_probe import read_ram, send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630

send(PORT, '{"cmd":"set_input","buttons":65519}')   # up, active low
time.sleep(0.5)
a = read_ram(PORT)
time.sleep(1.0)
b = read_ram(PORT)
send(PORT, '{"cmd":"clear_input"}')

diffs = [(i, a[i], b[i]) for i in range(min(len(a), len(b))) if a[i] != b[i]]
game = [(i, x, y) for i, x, y in diffs if 0x10000 <= i < 0x200000 and abs(y - x) <= 16]
print("changed bytes: %d  game-region small: %d" % (len(diffs), len(game)))
for i, x, y in game[:60]:
    print("  0x%06X  %d -> %d (%+d)" % (i, x, y, y - x))

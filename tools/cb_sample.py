#!/usr/bin/env python3
"""Sample the callback table 0x8005B900 periodically; report nonzero states."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
seen = collections.Counter()
for _ in range(300):
    r = send(PORT, '{"cmd":"read_ram","addr":"0x8005B8FC","len":40}')
    raw = bytes.fromhex(r["hex"])
    slots = tuple(int.from_bytes(raw[i * 4 + 4:i * 4 + 8], "little") for i in range(8))
    seen[slots] += 1
for slots, n in seen.most_common(6):
    print(n, "x", ["0x%08X" % s for s in slots])

#!/usr/bin/env python3
"""Read the per-frame callback table at 0x8005B900 (8 slots) and the counter."""
import sys

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
r = send(PORT, '{"cmd":"read_ram","addr":"0x8005B900","len":40}')
raw = bytes.fromhex(r["hex"])
for i in range(8):
    v = int.from_bytes(raw[i * 4:i * 4 + 4], "little")
    print("slot %d: 0x%08X" % (i, v))
print("counter @0x8005B920: 0x%08X" % int.from_bytes(raw[32:36], "little"))

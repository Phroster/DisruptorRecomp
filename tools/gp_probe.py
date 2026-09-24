#!/usr/bin/env python3
"""Probe candidate GP bases: values at gp+520 and gp+1188."""
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
CANDS = [0x800715E0, 0x80071490, 0x8007114C]

for gp in CANDS:
    a520 = gp + 520
    a1188 = gp + 1188
    for _ in range(3):
        b = bytes.fromhex(send(PORT, '{"cmd":"read_ram","addr":"0x%X","len":1}' % a520)["hex"])[0]
        w = int.from_bytes(bytes.fromhex(
            send(PORT, '{"cmd":"read_ram","addr":"0x%X","len":4}' % a1188)["hex"]), "little")
        print("gp=0x%08X  +520=0x%08X:%3d (0x%02X)  +1188=0x%08X:0x%08X"
              % (gp, a520, b, b, a1188, w))
        time.sleep(0.05)

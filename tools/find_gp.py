#!/usr/bin/env python3
"""Find the game's GP setup (lui $gp / addiu $gp) in the PSX-EXE."""
import struct

d = open("input/SLUS_002.24", "rb").read()
base = 0x80010000
for off in range(0, len(d) - 16, 4):
    w1 = struct.unpack_from("<I", d, off)[0]
    w2 = struct.unpack_from("<I", d, off + 4)[0]
    if (w1 >> 16) == 0x3C1C and (w2 >> 16) == 0x279C:
        hi = w1 & 0xFFFF
        lo = w2 & 0xFFFF
        if lo >= 0x8000:
            lo -= 0x10000
        gp = (hi << 16) + lo
        print("at 0x%08X: lui gp,0x%04X; addiu gp,gp,%d -> gp=0x%08X"
              % (base + off, hi, lo, gp))

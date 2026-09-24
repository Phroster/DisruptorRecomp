#!/usr/bin/env python3
"""Disassemble a range of the game executable (input/SLUS_002.24), branches included.

Usage: python tools/exe_disasm.py <hexstart> <hexend>
"""
import struct
import sys

sys.path.insert(0, "tools")
from mips_ram_disasm import dis

LOAD, HDR = 0x80010000, 0x800


def main():
    lo, hi = int(sys.argv[1], 16), int(sys.argv[2], 16)
    d = open("input/SLUS_002.24", "rb").read()
    for a in range(lo & ~3, hi, 4):
        w = struct.unpack_from("<I", d, a - LOAD + HDR)[0]
        print("%08X %08X  %s" % (a, w, dis(w, a)))


if __name__ == "__main__":
    main()

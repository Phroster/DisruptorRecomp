#!/usr/bin/env python3
"""List every kernel-RAM word the running game has changed from the BIOS image.

Usage: python tools/kernel_patch_diff.py        (game running, debug port 4624)

OpenBIOS copies its kernel text from ROM 0x1FC1E4D4.. to RAM 0x500..; the
game's Psy-Q patchers then overwrite a few words of it. Those words are code
that exists only at run time, so each patched run needs a native shard (see
warm_cache.ps1) or it interprets. This prints the patched runs so they can be
compared with the entries the shard cache covers.
"""
import json

from ask import ask

PORT = 4624
ROM_LO, ROM_HI, RAM_LO = 0x1E4D4, 0x22B74, 0x500


def main():
    rom = open('psxrecomp/bios/openbios.bin', 'rb').read()
    ram_hi = RAM_LO + (ROM_HI - ROM_LO)
    diff = []
    for base in range(RAM_LO, ram_hi, 0x400):
        n = min(0x400, ram_hi - base)
        r = ask(PORT, json.dumps({"cmd": "read_ram", "addr": "0x%08X" % (0x80000000 + base),
                                  "len": n}), timeout=10.0, tries=2)
        live = bytes.fromhex(r["hex"])
        ref = rom[ROM_LO + base - RAM_LO:ROM_LO + base - RAM_LO + n]
        diff += [base + i for i in range(0, n, 4) if live[i:i + 4] != ref[i:i + 4]]
    runs = []
    for a in diff:
        if runs and a == runs[-1][1] + 4:
            runs[-1][1] = a
        else:
            runs.append([a, a])
    print("kernel RAM words that differ from the BIOS ROM image: %d, in %d runs"
          % (len(diff), len(runs)))
    for lo, hi in runs:
        print("   0x%04X..0x%04X (%d words)" % (lo, hi + 4, int((hi - lo) / 4) + 1))


if __name__ == '__main__':
    main()

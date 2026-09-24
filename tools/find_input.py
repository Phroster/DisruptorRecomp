#!/usr/bin/env python3
"""Find the game's input handler: functions that call the pad read and then
test direction bits (andi 0x10/0x20/0x40/0x80).

Usage: python tools/find_input.py
"""
import glob
import re
import sys

PAD_FUNCS = ("func_8004FDB4", "func_8004FC9C", "func_8004FC3C",
             "func_8004FCCC", "func_8004FD40", "func_8004FD84")
DIR_RE = re.compile(r"/\* (0x[0-9A-Fa-f]+): 0x[0-9A-Fa-f]{2}(10|20|40|80)00[0-9A-Fa-f]{4} \*/")
FUNC_RE = re.compile(r"^(?:static )?(?:void|u?int\w*) (func_[0-9A-Fa-f]+)\(")


def main():
    hits = {}
    for path in glob.glob("generated/*.c"):
        cur = "?"
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        for i, line in enumerate(lines):
            m = FUNC_RE.match(line)
            if m:
                cur = m.group(1)
            if any(f + "(" in line for f in PAD_FUNCS):
                window = lines[i:i + 120]
                masks = set()
                for w in window:
                    dm = re.search(r"& 0x00(10|20|40|80);  /\* (0x[0-9A-Fa-f]+)", w)
                    if dm:
                        masks.add(dm.group(1))
                if masks:
                    hits.setdefault(cur, set()).update(masks)
    for fn, masks in sorted(hits.items()):
        if len(masks) >= 2:
            print(f"{fn}: direction masks {sorted(masks)}")


if __name__ == "__main__":
    main()

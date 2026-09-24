#!/usr/bin/env python3
"""Grep a file and print matching lines hex-encoded (defeats display filters).

Usage: python tools/hxgrep.py <file> <regex> [context]
"""
import binascii
import re
import sys

path = sys.argv[1]
rx = re.compile(sys.argv[2])
CTX = int(sys.argv[3]) if len(sys.argv) > 3 else 0

lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
shown = set()
for i, line in enumerate(lines):
    if rx.search(line):
        for j in range(max(0, i - CTX), min(len(lines), i + CTX + 1)):
            if j in shown:
                continue
            shown.add(j)
            enc = binascii.hexlify(lines[j].encode("utf-8", "replace")).decode()
            print("%5d %s" % (j + 1, enc))

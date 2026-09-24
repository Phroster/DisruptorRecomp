#!/usr/bin/env python3
"""Append the remaining frame-sync wait patches to game.toml."""
import io

SITES = ["0x800205C8", "0x80020B68", "0x80043590", "0x800438B8",
         "0x80043E80", "0x80043EA0", "0x80044604", "0x800485C0"]

p = "game.toml"
s = io.open(p, encoding="utf-8").read()
adds = []
for i, a in enumerate(SITES):
    adds.append(
        '[[recompiler.patch]]\n'
        'id = "loop-wait-%02d"\n'
        'address = "%s"\n'
        'expected = "0x00002021"\n'
        'replacement = "0x2404FFFF"\n'
        'note = "frame-sync call a0=0 to a0=-1 (60 fps engine mod)"\n'
        % (i, a))
if "loop-wait-00" not in s:
    s = s.replace("[runtime]", "\n".join(adds) + "\n[runtime]", 1)
    io.open(p, "w", encoding="utf-8").write(s)
    print("added", len(adds), "patches")
else:
    print("already present")

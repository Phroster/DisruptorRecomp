#!/usr/bin/env python3
"""List debug-server command names from the table."""
import io
import re

s = io.open("psxrecomp/runtime/src/debug_server.c", encoding="utf-8",
            errors="replace").read()
i = s.find('{ "gl_present_ring"')
seg = s[i - 12000:i + 400]
names = re.findall(r'\{\s*"([a-z_0-9]+)"', seg)
print(len(names), "commands")
for n in names:
    print(n)

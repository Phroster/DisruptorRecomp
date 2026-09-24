#!/usr/bin/env python3
"""Arm fntrace on a target function and read back call-site RAs."""
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625
TARGET = sys.argv[2] if len(sys.argv) > 2 else "0x8004EE24"

print(send(PORT, '{"cmd":"fntrace_arm","target":"%s"}' % TARGET))
print(send(PORT, '{"cmd":"fntrace_armed"}'))
time.sleep(1.0)
d = send(PORT, '{"cmd":"fntrace_dump","target_lo":"%s","target_hi":"0x%08X","count":24}'
         % (TARGET, int(TARGET, 16) + 1))
print("total:", d.get("total"), "entries:", len(d.get("entries", [])))
for e in d.get("entries", [])[:24]:
    print(" ", e)
send(PORT, '{"cmd":"fntrace_arm_clear"}')

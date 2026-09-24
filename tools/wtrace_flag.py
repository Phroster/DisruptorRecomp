#!/usr/bin/env python3
"""Write-trace the dispatcher flag 0x80071934 (physical 0x71934)."""
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630

print(send(PORT, '{"cmd":"wtrace_del"}'))
print(send(PORT, '{"cmd":"wtrace_range","lo":"0x71934","hi":"0x71938"}'))
time.sleep(1.0)
d = send(PORT, '{"cmd":"wtrace_dump","count":32}')
print("total:", d.get("total"), "emitted:", d.get("emitted"))
for e in d.get("entries", [])[:32]:
    print(" ", e)
print(send(PORT, '{"cmd":"wtrace_del"}'))

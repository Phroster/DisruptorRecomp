#!/usr/bin/env python3
"""Dump the interpreted-instruction ring and histogram hot PCs.

Usage: python tools/insn_hist.py <port> [count]
Saves raw reply to logs/insn.json.
"""
import collections
import json
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4634
TOP = int(sys.argv[2]) if len(sys.argv) > 2 else 30

with socket.create_connection(("127.0.0.1", PORT), timeout=60) as s:
    s.sendall(b'{"cmd":"dirty_insn_log"}\n')
    s.settimeout(60)
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c:
            break
        buf += c
open("logs/insn.json", "wb").write(buf)
try:
    d = json.loads(buf.decode(errors="replace"))
except Exception as e:
    print("json parse failed:", e)
    sys.exit(1)

print("top-level keys:", sorted(d.keys())[:20])
entries = None
for k, v in d.items():
    if isinstance(v, list) and v and isinstance(v[0], dict):
        entries = v
        print("entries key: %s  n=%d" % (k, len(v)))
        print("entry keys:", sorted(v[0].keys()))
        print("sample:", json.dumps(v[0])[:300])
        break
if entries is None:
    print(json.dumps(d)[:2000])
    sys.exit(0)

cnt = collections.Counter()
for e in entries:
    pc = e.get("pc") or e.get("pc0") or e.get("addr")
    if pc is None:
        continue
    cnt[pc if isinstance(pc, str) else "0x%08X" % pc] += 1

print("distinct PCs:", len(cnt))
for pc, c in cnt.most_common(TOP):
    v = int(pc, 16)
    phys = v & 0x1FFFFFFF
    print("  %s  phys=0x%08X  x%d" % (pc, phys, c))

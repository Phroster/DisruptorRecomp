#!/usr/bin/env python3
"""Read guest RAM and locate the same bytes inside WAD.IN.

Usage: python tools/ram_find.py <port> <addr> <len> [needle-bytes]
"""
import json
import socket
import sys

PORT = int(sys.argv[1])
ADDR = sys.argv[2]
LEN = int(sys.argv[3], 0)
NEEDLE = int(sys.argv[4], 0) if len(sys.argv) > 4 else 64

with socket.create_connection(("127.0.0.1", PORT), timeout=60) as s:
    s.sendall(('{"cmd":"read_ram","addr":"%s","len":%d}\n'
               % (ADDR, LEN)).encode())
    s.settimeout(60)
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c:
            break
        buf += c
r = json.loads(buf.decode(errors="replace"))
if not r.get("ok"):
    print("read_ram failed:", r)
    sys.exit(1)
blob = bytes.fromhex(r["hex"])
print("read %d bytes from %s" % (len(blob), ADDR))

d = open(".local/WAD.IN", "rb").read()
hits = []
start = 0
while True:
    i = d.find(blob[:NEEDLE], start)
    if i < 0:
        break
    hits.append(i)
    start = i + 1
print("WAD.IN hits for first %d bytes: %s" % (NEEDLE, [hex(h) for h in hits[:10]]))
for h in hits[:5]:
    print("  at 0x%X sector %d  match_len=%d of %d"
          % (h, h // 2048, len(os.path.commonprefix([blob, d[h:h + len(blob)]])),
             len(blob)))
import os

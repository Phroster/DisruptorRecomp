#!/usr/bin/env python3
"""Save guest RAM to .local and probe WAD.IN for prefix matches + sample regions.

Usage: python tools/wad_probe.py <port> <addr> <len>
"""
import json
import os
import socket
import sys

PORT = int(sys.argv[1])
ADDR = sys.argv[2]
LEN = int(sys.argv[3], 0)

with socket.create_connection(("127.0.0.1", PORT), timeout=60) as s:
    s.sendall(('{"cmd":"read_ram","addr":"%s","len":%d}\n' % (ADDR, LEN)).encode())
    s.settimeout(60)
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c:
            break
        buf += c
r = json.loads(buf.decode(errors="replace"))
blob = bytes.fromhex(r["hex"])
out = ".local/ram_%s.bin" % ADDR.replace("0x", "")
open(out, "wb").write(blob)
print("saved", out, len(blob), "bytes")

d = open(".local/WAD.IN", "rb").read()
for n in (8, 12, 16, 24, 32):
    hits = []
    start = 0
    while len(hits) < 5:
        i = d.find(blob[:n], start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    print("needle %2d bytes -> hits %s" % (n, [hex(h) for h in hits]))

print()
for off in (0, 0x7800, 0xD3800, 0x83E000, 0x857000, 0x400000):
    row = d[off:off + 32]
    print("%08X %s  %s" % (off, row.hex(), "".join(
        chr(c) if 32 <= c < 127 else "." for c in row)))

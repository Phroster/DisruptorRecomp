#!/usr/bin/env python3
"""Send a debug command and save the raw reply to a file.

Usage: python tools/dump_cmd.py <port> <cmd> <outfile> [json-extra]
"""
import socket
import sys

PORT = int(sys.argv[1])
CMD = sys.argv[2]
OUT = sys.argv[3]
EXTRA = sys.argv[4] if len(sys.argv) > 4 else ""

payload = '{"cmd":"%s"%s}' % (CMD, ("," + EXTRA) if EXTRA else "")

with socket.create_connection(("127.0.0.1", PORT), timeout=60) as s:
    s.sendall((payload + "\n").encode())
    s.settimeout(60)
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c:
            break
        buf += c
open(OUT, "wb").write(buf)
print("%s -> %s (%d bytes)" % (CMD, OUT, len(buf)))

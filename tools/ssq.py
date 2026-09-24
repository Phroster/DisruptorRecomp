#!/usr/bin/env python3
"""Send {"cmd":"savestate"} and dump the full reply.

Usage: python tools/ssq.py <port> load|save [slot] [status]
"""
import socket
import sys

port = int(sys.argv[1])
op = sys.argv[2] if len(sys.argv) > 2 else "load"
slot = int(sys.argv[3]) if len(sys.argv) > 3 else 3
if len(sys.argv) > 4 and sys.argv[4] == "status":
    payload = '{"cmd":"savestate_status"}'
else:
    payload = '{"cmd":"savestate","op":"%s","slot":%d}' % (op, slot)

with socket.create_connection(("127.0.0.1", port), timeout=30) as s:
    s.sendall((payload + "\n").encode())
    s.settimeout(30)
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
print(payload)
print(buf.decode(errors="replace")[:2000])

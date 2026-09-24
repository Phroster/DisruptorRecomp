#!/usr/bin/env python3
"""Extract debug-server commands matching a regex and print names hex-encoded
(defeats any display-level string substitutions), then optionally probe them.

Usage:
  python tools/find_cmd.py <regex>            # list matching names as hex
  python tools/find_cmd.py <regex> --probe    # also send {"cmd":NAME}
  python tools/find_cmd.py <regex> --full     # print full replies on match
"""
import binascii
import re
import socket
import sys

REGEX = sys.argv[1] if len(sys.argv) > 1 else "."
PROBE = "--probe" in sys.argv
FULL = "--full" in sys.argv
PORT = 4634

src = open("psxrecomp/runtime/src/debug_server.c", encoding="utf-8",
           errors="replace").read()

pairs = re.findall(r'\{\s*"([^"]{1,48})"\s*,\s*&?([A-Za-z_0-9]+)\s*\}', src)
rx = re.compile(REGEX, re.I)
seen = set()
hits = []
for name, handler in pairs:
    if name in seen:
        continue
    seen.add(name)
    if rx.search(name) or rx.search(handler):
        hits.append((name, handler))


def send(payload):
    with socket.create_connection(("127.0.0.1", PORT), timeout=30) as s:
        s.sendall((payload + "\n").encode())
        s.settimeout(30)
        buf = b""
        while not buf.endswith(b"\n"):
            c = s.recv(1 << 20)
            if not c:
                break
            buf += c
    return buf.decode(errors="replace")


print("%d matching entries" % len(hits))
for name, handler in hits:
    line = "name=%s handler=%s" % (
        binascii.hexlify(name.encode()).decode(), handler)
    if PROBE or FULL:
        try:
            r = send('{"cmd":"%s"}' % name)
        except Exception as e:
            r = "EXC %s" % e
        ok = '"ok":true' in r
        line += "  ok=%s len=%d" % (ok, len(r))
        if FULL:
            line += "\n    " + r[:1500]
    print(line)

#!/usr/bin/env python3
"""Query a debug command on a chosen port: q.py <port> <cmd> [json args]"""
import json
import sys

sys.path.insert(0, "tools")
from input_probe import send

port = int(sys.argv[1])
cmd = sys.argv[2]
extra = (" " + sys.argv[3]) if len(sys.argv) > 3 else ""
payload = '{"cmd":"%s"%s}' % (cmd, ("," + extra) if extra else "")
r = send(port, payload)
print(json.dumps(r, indent=1)[:2200])

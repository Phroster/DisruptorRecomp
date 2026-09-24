#!/usr/bin/env python3
import json
import sys

from input_probe import send

port = int(sys.argv[1]) if len(sys.argv) > 1 else 4625
for cmd in ('"pace_state"', '"vblank_rate"', '"timers_state"'):
    try:
        print(cmd, "->", json.dumps(send(port, '{"cmd":%s}' % cmd))[:600])
    except Exception as exc:
        print(cmd, "ERR", exc)

#!/usr/bin/env python3
"""Dump frame_perf from a live instance."""
import json
import sys

sys.path.insert(0, "tools")
from input_probe import send

port = int(sys.argv[1]) if len(sys.argv) > 1 else 4624
r = send(port, '{"cmd":"frame_perf"}')
print(json.dumps(r, indent=1)[:2600])

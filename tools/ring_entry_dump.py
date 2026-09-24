#!/usr/bin/env python3
import json

from input_probe import send

r = send(4624, '{"cmd":"gte_ring_dump","count":2,"newest":1}')
e = r["entries"][-1]
print(sorted(e.keys()))
print(json.dumps({k: v for k, v in e.items() if k != "RT"}, indent=1))
print("RT[0:4]:", e["RT"][:4])

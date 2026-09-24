#!/usr/bin/env python3
"""DMA state + recent GPU DMA kicks (channel 2) with their initiator PCs."""
import json
import sys

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625

st = send(PORT, '{"cmd":"dma_state"}')
print("dma_state:", json.dumps(st)[:600])
tr = send(PORT, '{"cmd":"dma_trace_dump","count":24}')
print("dma_trace keys:", sorted(tr.keys()))
ev = tr.get("entries") or tr.get("events") or []
for e in ev[:24]:
    print(" ", e)

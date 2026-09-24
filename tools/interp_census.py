#!/usr/bin/env python3
"""Native-vs-interpreted census of the running game.

Usage: python tools/interp_census.py <seconds> [press]

Samples dispatch_stats, overlay_loader_status and dirty_ram_stats at the start
and end of the window and prints the deltas plus the interpreted PCs. With
"press" it taps Start/Cross alternately to walk through menus headlessly.
Target: dirty-RAM interpreter +0 blocks / +0 insns.
"""
import json, sys, time
from ask import ask
from input_probe import BUTTONS, send
PORT = 4624
def q(cmd, **kw):
    d = {"cmd": cmd}; d.update(kw)
    return ask(PORT, json.dumps(d), timeout=10.0, tries=3)
def snap():
    d = q("dirty_ram_stats"); o = q("overlay_loader_status"); s = q("dispatch_stats")
    return d, o, s
secs = int(sys.argv[1]); press = len(sys.argv) > 2 and sys.argv[2] == 'press'
d0, o0, s0 = snap()
end = time.time() + secs; i = 0
while time.time() < end:
    if press:
        b = 0xFFFF & ~BUTTONS["start" if i % 2 == 0 else "cross"]
        send(PORT, '{"cmd":"press","buttons":%d,"frames":4}' % b)
    time.sleep(2.5); i += 1
d1, o1, s1 = snap()
print("frame:", q("ping"))
print("static native dispatches: +%d  misses: +%d" % (s1["static_hits"]-s0["static_hits"], s1["miss_total"]-s0["miss_total"]))
print("overlay-shard native: +%d   interp fallback: +%d   shards loaded: %d" % (o1["dispatch_native"]-o0["dispatch_native"], o1["dispatch_interp_fallback"]-o0["dispatch_interp_fallback"], o1["loads"]))
print("dirty-RAM interpreter: blocks +%d  insns +%d  handoffs +%d" % (d1["blocks_run"]-d0["blocks_run"], d1["insns_run"]-d0["insns_run"], d1["native_handoffs"]-d0["native_handoffs"]))
h0 = {p["pc"]: p["insns"] for p in d0["per_pc"]}
rows = [(p["insns"]-h0.get(p["pc"],0), p["pc"], p["ext_ra"]) for p in d1["per_pc"]]
for n, pc, ra in sorted(rows, reverse=True)[:14]:
    if n: print("   interp pc %s  +%d insns  (ra %s)" % (pc, n, ra))

#!/usr/bin/env python3
"""Sample engine globals near GP across draw/empty frames."""
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630

regs = send(PORT, '{"cmd":"get_registers"}')
print("get_registers keys:", sorted(regs.keys()))
gp = None
for k in ("gpr", "regs", "registers"):
    if k in regs:
        gp = regs[k][28]
print("gp:", gp)
if gp is None:
    print(regs)
    sys.exit(0)

gp = int(gp, 16) if isinstance(gp, str) else gp
A520 = gp + 520
A1188 = gp + 1188
print("gp=0x%08X  +520=0x%08X  +1188=0x%08X" % (gp, A520, A1188))


def rd8(a):
    return int(send(PORT, '{"cmd":"read_ram","addr":"0x%X","len":1}' % a)["hex"], 16)


def rd32(a):
    return int(send(PORT, '{"cmd":"read_ram","addr":"0x%X","len":4}' % a)["hex"], 16)


st = send(PORT, '{"cmd":"gpu_ring_stats"}')
newest = st["newest_frame"]
drawn = set()
for f in range(newest - 8, newest + 1):
    r = send(PORT, '{"cmd":"gpu_frame_dump","frame":%d,"count":4}' % f)
    if r.get("count", 0) > 0:
        drawn.add(f)
print("drawn frames:", sorted(drawn))

for i in range(20):
    st = send(PORT, '{"cmd":"gpu_ring_stats"}')
    f = st["newest_frame"]
    v520 = rd8(A520)
    v1188 = rd32(A1188)
    print("frame %d %-5s  +520=%3d  +1188=0x%08X" %
          (f, "DRAW" if f in drawn or (f % 2) in [d % 2 for d in drawn] else "empty",
           v520, v1188))
    time.sleep(0.02)

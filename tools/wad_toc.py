#!/usr/bin/env python3
"""Analyze the WAD.IN table of contents: test record layouts against the file.

Usage: python tools/wad_toc.py
"""
import struct

WAD = ".local/WAD.IN"
N = 4096
data = open(WAD, "rb").read(N * 4)
fsize = 191963136
SECT = 2048
nsect_total = fsize // SECT

v = list(struct.unpack_from("<%dI" % N, data, 0))
print("first 16:", v[:16])
print("first 16 //2048:", [x // SECT for x in v[:16]])
print("all mult of 2048 (first %d)? %s" % (N, all(x % SECT == 0 for x in v)))

sect = [x // SECT for x in v]

# find the longest run of strictly increasing values starting anywhere in v
best_i, best_n = 0, 0
i = 0
while i < N:
    j = i
    while j + 1 < N and sect[j] < sect[j + 1]:
        j += 1
    if j - i > best_n:
        best_i, best_n = i, j - i
    i = j + 1
print("longest increasing run: start idx %d len %d" % (best_i, best_n))
print("  values", sect[best_i:best_i + 8])

# cumulative-sum interpretation: are the values sector SIZES of contiguous
# entries?  Check sum of first k values vs plausible TOC end / file size.
cum = 0
for k in range(1, 12):
    cum += sect[k - 1]
    print("  cum after %d values: %d sectors (%d bytes)" % (k, cum, cum * SECT))

# 8-byte records (offset,size) starting at 0 and at 1
for start in (0, 1, 2):
    pairs = [(sect[i], sect[i + 1]) for i in range(start, 200, 2)]
    mono = all(p[0] < p[1] and (i == 0 or pairs[i - 1][0] + pairs[i - 1][1] <= p[0])
               for i, p in enumerate(pairs))
    print("pairs @%d (o,sz) first4 %s monotonic_nonoverlap=%s"
          % (start, pairs[:4], mono))

#!/usr/bin/env python3
"""Analyze saved frame access logs: first divergence in main-RAM game accesses."""
import json
import sys


def load(p):
    return json.load(open(p))["entries"]


def game(entries):
    out = []
    for e in entries:
        a = int(e["addr"], 16)
        if 0x10000 <= a < 0x200000:
            out.append(e)
    return out


def first_diff(a, b, label, limit=6):
    n = min(len(a), len(b))
    for i in range(n):
        x, y = a[i], b[i]
        if (x["kind"], x["addr"], x["val"], x["pc"]) != (y["kind"], y["addr"], y["val"], y["pc"]):
            print("== %s: first game-RAM divergence at %d/%d" % (label, i, n))
            for j in range(max(0, i - 2), min(n, i + limit)):
                m = " *" if j == i else "  "
                p, q = a[j], b[j]
                print("%s[%d] A %s %s=%s pc=%s cyc=%s" %
                      (m, j, p["kind"], p["addr"], p["val"], p["pc"], p.get("cyc")))
                print("%s[%d] B %s %s=%s pc=%s cyc=%s" %
                      (m, j, q["kind"], q["addr"], q["val"], q["pc"], q.get("cyc")))
            return i
    print("== %s: no game-RAM divergence in %d entries" % (label, n))
    return None


d1 = game(load("logs/frame_d1.json"))
e = game(load("logs/frame_e.json"))
d2 = game(load("logs/frame_d2.json"))
print("game-RAM entries: d1=%d empty=%d d2=%d" % (len(d1), len(e), len(d2)))
first_diff(d1, e, "draw vs empty")
first_diff(d1, d2, "draw vs draw (control)")

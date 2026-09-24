#!/usr/bin/env python3
"""PGXP coverage over a 5 s window: how many GPU vertices got a precise
(sub-pixel) position and how many triangles perspective-correct UVs.

Usage: python tools/pgxp_census.py [--seconds 5]
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=20.0, tries=2)


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 5.0
    d0 = q("geom_correction")
    time.sleep(secs)
    d1 = q("geom_correction")
    p0, p1 = d0["pgxp"], d1["pgxp"]
    dd = {k: p1[k] - p0[k] for k in p1 if isinstance(p1[k], int) and k not in ("enabled", "cpu_mode")}
    look = max(1, dd["lookups"])
    print("pgxp enabled=%d cpu_mode=%d tolerance=%s" % (p1["enabled"], p1["cpu_mode"], p1["tolerance"]))
    print("vertex lookups %d: dataflow %.1f%%  fallback %.1f%%  native %.1f%%" % (
        dd["lookups"], 100.0 * dd["dataflow_hit"] / look, 100.0 * dd["fallback_hit"] / look,
        100.0 * dd["native"] / look))
    print("produced %d  swc2_stores %d  value_mismatch %d  trunc_reject %d  tolerance_reject %d  w_valid %d" % (
        dd["produced"], dd["swc2_stores"], dd["value_mismatch"], dd["trunc_reject"],
        dd["tolerance_reject"], dd["w_valid"]))
    t0, t1 = d0["texcorr"], d1["texcorr"]
    print("perspective: triangles %d | attempts %d armed %d no_source %d no_depth %d" % (
        d1["perspective_triangles"] - d0["perspective_triangles"],
        t1["attempts"] - t0["attempts"], t1["armed"] - t0["armed"],
        t1["no_source"] - t0["no_source"], t1["no_depth"] - t0["no_depth"]))


if __name__ == "__main__":
    main()

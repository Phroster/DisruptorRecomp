#!/usr/bin/env python3
"""Record every frame's timing while the user plays, for spike attribution.

Usage: python tools/frametime_record.py [--seconds 120] [--out logs/frametimes.json]
                                        [--no-wait]

Waits (up to 6 min) for gameplay - the first 16:9 frames in frame_perf - then
polls the always-on latency ring once a second and merges the per-frame
records by frame number, so no frame is missed (differences are taken inside
each response because the ring's timestamps are response-relative). Also samples frame_perf, phase_profile, dirty_ram_stats and
overlay_loader_status every 5 s. Analyse with tools/frametime_report.py.
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(cmd, **kw):
    d = {"cmd": cmd}
    d.update(kw)
    try:
        return ask(PORT, json.dumps(d), timeout=5.0, tries=2)
    except Exception:
        return None


def main():
    a = sys.argv[1:]
    secs = int(a[a.index("--seconds") + 1]) if "--seconds" in a else 120
    out = a[a.index("--out") + 1] if "--out" in a else "logs/frametimes.json"
    if "--no-wait" not in a:
        t0 = time.time()
        while time.time() - t0 < 360:
            fp = q("frame_perf")
            if fp and fp.get("ok") and fp.get("wide_frames", 0) > 32:
                break
            time.sleep(2)
        print("gameplay detected after %.0f s (or timeout); recording %d s"
              % (time.time() - t0, secs), flush=True)
    frames, samples = {}, []
    start = time.time()
    nxt = 0.0
    while time.time() - start < secs:
        r = q("latency", window=300, raw=1, count=300)
        rf = (r or {}).get("frames", [])
        # Timestamps are relative to each response, so differences are only
        # meaningful between frames of the SAME response: compute them here.
        for fa, fb in zip(rf, rf[1:]):
            if fb["f"] != fa["f"] + 1 or fb["f"] in frames:
                continue
            if max(fa.get("paced", 0), fb.get("paced", 0)) > 1e15:
                continue
            # Frames the runtime did not present (unchanged picture during
            # BIOS/menus) carry stale or missing swap marks: skip them.
            if not (0 <= fa["swap_begin"] < fa["swap_end"] < fb["swap_begin"] < fb["swap_end"]):
                continue
            late_pace = fb["paced"] > fb["swap_begin"]      # deferred pacing (DXGI path)
            frames[fb["f"]] = {
                "f": fb["f"],
                "d_present": fb["swap_end"] - fa["swap_end"],
                "d_paced": fb["paced"] - fa["paced"],
                "prep": (fb["paced"] if late_pace else fb["swap_end"]) - fb["swap_begin"],
                "flip_call": (fb["swap_end"] - fb["paced"]) if late_pace else 0.0,
                "deferred": 1 if late_pace else 0,
            }
        now = time.time() - start
        if now >= nxt:
            nxt = now + 5.0
            samples.append({"t": round(now, 1), "frame_perf": q("frame_perf"),
                            "phase_profile": q("phase_profile", window=5),
                            "dirty": q("dirty_ram_stats"),
                            "overlay": q("overlay_loader_status"),
                            "last_f": max(frames) if frames else None})
        time.sleep(1.0)
    with open(out, "w") as fh:
        json.dump({"seconds": secs, "frames": [frames[k] for k in sorted(frames)],
                   "samples": samples}, fh)
    print("recorded %d frames -> %s" % (len(frames), out), flush=True)


if __name__ == "__main__":
    main()

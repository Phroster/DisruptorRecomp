#!/usr/bin/env python3
"""Capture the kernel page in its short-lived boot state.

Usage: python tools/capture_boot_window.py [--out build/overlay_captures_boot.json]

Start the game first (cold boot), then run this immediately. Disruptor's
Psy-Q patchers install the card stub at 0x281C about half a second before
they patch the exception-handler prologue at 0x27B4. The periodic overlay
capture only ever sees the final state, so the shard cache has nothing that
matches the intermediate one and every exception in that window interprets
(~32k instructions per boot). This tool polls the live game and, the moment
the stub appears while the prologue still holds its boot bytes, snapshots the
real page as an overlay capture record.
Compile the result with psxrecomp/tools/compile_overlays.py --captures <out>.
"""
import base64
import json
import sys
import time

from ask import ask

PORT = 4624
PAGE = 0x80002000
SIZE = 4096
GUARD = 4
STUB = 0x8000281C
SLOT = 0x800027B4
SLOT_LEN = 0x30


def q(cmd, timeout=3.0, **kw):
    d = {"cmd": cmd}
    d.update(kw)
    try:
        return ask(PORT, json.dumps(d), timeout=timeout, tries=1)
    except Exception:
        return None


def read_page():
    out = b""
    while len(out) < SIZE + GUARD:
        n = min(0x400, SIZE + GUARD - len(out))
        r = q("read_ram", addr="0x%08X" % (PAGE + len(out)), len=n)
        if not r or not r.get("ok"):
            return None
        out += bytes.fromhex(r["hex"])
    return out


def main():
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else \
        "build/overlay_captures_boot.json"
    end = time.time() + 60
    slot = None  # prologue bytes last seen while the stub was still absent
    while time.time() < end:
        r = q("read_ram", addr="0x%08X" % SLOT, len=SLOT_LEN)
        t = q("read_ram", addr="0x%08X" % STUB, len=16)
        if not r or not t or not r.get("ok") or not t.get("ok"):
            time.sleep(0.02)
            continue
        if int(t["hex"], 16) == 0:
            if int(r["hex"], 16) != 0:
                slot = r["hex"]     # kernel copied to RAM, nothing patched yet
            time.sleep(0.02)
            continue
        if slot is None or r["hex"] != slot:
            print("too late: the kernel page is already in its final state")
            return 1
        before = read_page()
        after = read_page()
        if not before or before != after:
            print("page changed while reading; rerun on a fresh boot")
            return 1
        d = q("dirty_ram_stats") or {"insns_run": -1}
        pcs = ["0x%08X" % (STUB + 4 * i) for i in range(4)]
        rec = [{
            "schema": "psxrecomp overlay capture v2",
            "load_addr": "0x%08X" % PAGE,
            "size": SIZE + GUARD,
            "guard_bytes": GUARD,
            "bytes_b64": base64.b64encode(before).decode(),
            "executed_pcs": pcs,
            "dispatch_entry_pcs": [pcs[0]],
            "function_entry_pcs": [],
            "seeds": [pcs[0]],
        }]
        with open(out, "w") as fh:
            json.dump(rec, fh)
        print("captured intermediate kernel page (interp insns so far: %d) -> %s"
              % (d["insns_run"], out))
        return 0
    print("timed out waiting for the boot window")
    return 1


if __name__ == "__main__":
    sys.exit(main())

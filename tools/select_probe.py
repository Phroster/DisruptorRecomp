#!/usr/bin/env python3
"""Watch the game's weapon / psionic selection while input is injected.

Usage: python tools/select_probe.py [--script "w-1;s0.5;w-1,w-1;s1"] [--own 3,4,5]
       (state loaded; --own marks those weapons owned in RAM for the test - the
       weapon list holds weapon 1 or 2 plus every owned weapon 3..9)

Script steps, ';'-separated: "w<n>" = mouse wheel notch(es) (n>0 up, n<0 down;
"w-1,-1" = two notches back to back), "b<name>[+<name>]=<sec>" = hold pad
button(s) (tools/input_probe.py names) for sec seconds - a whole-pad override that
bypasses the keybind layer, "k<key>=<1|0>" = hold / release a host key through
keybinds.ini (debug verb host_key; merges with the wheel mod), "s<sec>" = wait.
--psi 0,1,2 marks those psionic powers owned (ownership table 0x80077B5C). While it runs the
game state is sampled continuously and printed whenever it changes:

  frame   engine frame counter (gp+1452)
  st      input state byte gp+784 (0 play, 2 weapon list, 3 psionic list, 4 pause, ...)
  btn     the game's button word 0x80077670 (L1=0004 R1=0008 Select=0100 Start=0800 ...)
  wpn     0x80077627 selected weapon / gp+824 weapon in hand, 0x80077628 other weapon
  psi     0x80077629 current psionic, 0x8007762A other psionic
"""
import json
import struct
import sys
import threading
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624
GP = 0x8007114C


def q(**k):
    return ask(PORT, json.dumps(k), timeout=10.0, tries=2)


def rd(addr, n):
    r = q(cmd="read_ram", addr="0x%08X" % addr, len=n)
    return bytes.fromhex(r.get("hex") or r.get("data") or "")


def sample():
    g = rd(GP, 0x800)
    b = rd(0x80077620, 0x60)
    frame = struct.unpack_from("<I", g, 1452)[0]
    st = g[784]
    btn = struct.unpack_from("<I", b, 0x50)[0]
    return frame, st, btn, b[7], g[824], b[8], b[9], b[10]


def run_script(script, events):
    for step in script.split(";"):
        step = step.strip()
        if not step:
            continue
        if step[0] == "w":
            for part in step[1:].split(","):
                n = int(part.lstrip("w"))
                events.append((time.time(), "wheel %d" % n))
                q(cmd="host_mouse", wheel=n)
        elif step[0] == "b":
            name, sec = step[1:].split("=")
            mask = 0xFFFF
            for nm in name.split("+"):
                mask &= ~BUTTONS[nm]
            events.append((time.time(), "hold %s %ss" % (name, sec)))
            q(cmd="set_input", buttons=mask)
            time.sleep(float(sec))
            q(cmd="clear_input")
            events.append((time.time(), "release %s" % name))
        elif step[0] == "k":
            key, down = step[1:].split("=")
            events.append((time.time(), "key %s %s" % (key, "down" if down == "1" else "up")))
            q(cmd="host_key", key=key, down=int(down))
        elif step[0] == "s":
            time.sleep(float(step[1:]))


def main():
    a = sys.argv[1:]
    script = a[a.index("--script") + 1] if "--script" in a else "s0.5;w-1;s1.0;w1;s1.0"
    g = rd(GP, 64)
    m24, m28 = struct.unpack_from("<II", g, 24)
    print("weapon-button mask gp+24 = 0x%04X, psionic-button mask gp+28 = 0x%04X" % (m24, m28))
    if "--own" in a:
        for w in a[a.index("--own") + 1].split(","):
            q(cmd="write_ram", addr="0x%08X" % (0x80077100 + 4 * (int(w) - 3)), val="0x01")
        time.sleep(0.2)
    if "--psi" in a:
        for i in a[a.index("--psi") + 1].split(","):
            q(cmd="write_ram", addr="0x%08X" % (0x80077B5C + 4 * int(i)), val="0x01")
        time.sleep(0.2)
    q(cmd="clear_input")
    log, stop = [], [False]

    def watcher():
        last = None
        while not stop[0]:
            try:
                s = sample()
            except Exception as e:           # keep watching; say so in the log
                log.append((time.time(), "sample failed: %s" % e))
                time.sleep(0.2)
                continue
            if s[1:] != (last[1:] if last else None):
                log.append((time.time(), s))
                last = s

    t = threading.Thread(target=watcher, daemon=True)
    t.start()
    events = [(time.time(), "start")]
    try:
        run_script(script, events)
        time.sleep(0.3)
    finally:
        q(cmd="clear_input")
        for key in ("Q", "R", "W", "S"):
            q(cmd="host_key", key=key, down=0)
        stop[0] = True
        t.join(timeout=5)
    t0 = events[0][0]
    rows = [(tt, "EVENT " + e) for tt, e in events] +            [(tt, s if isinstance(s, str) else
             "frame %6d st %d btn %04X wpn %d in hand %d other %d psi %d/%d" % s) for tt, s in log]
    for tt, text in sorted(rows):
        print("%7.3f  %s" % (tt - t0, text))


if __name__ == "__main__":
    main()

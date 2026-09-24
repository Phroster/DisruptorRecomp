#!/usr/bin/env python3
"""3D scene submission rate: rotate the camera with the pad and count how often
the newest GTE camera matrix changes, plus how often the camera position moves."""
import time

from input_probe import send

# Player/camera position candidates near the yaw byte.
POS_WORDS = [0x80077628, 0x8007762C, 0x80077630]


def newest_rt(port):
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    return tuple(r["entries"][-1]["RT"])


def word(port, addr):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":2}' % addr)
    return int(r["hex"], 16)


def main():
    port = 4624
    send(port, '{"cmd":"set_input","buttons":65503}')
    time.sleep(0.3)

    rt_samples = []
    pos_samples = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 3.0:
        t = time.perf_counter() - t0
        rt_samples.append((t, newest_rt(port)))
        pos_samples.append((t, tuple(word(port, a) for a in POS_WORDS)))
        time.sleep(0.004)
    send(port, '{"cmd":"clear_input"}')

    span = rt_samples[-1][0] - rt_samples[0][0]
    rt_changes = sum(1 for (_, a), (_, b) in zip(rt_samples, rt_samples[1:]) if a != b)
    pos_changes = sum(1 for (_, a), (_, b) in zip(pos_samples, pos_samples[1:]) if a != b)
    print("span=%.2fs RT changes=%d (%.1f Hz)  pos changes=%d (%.1f Hz)" %
          (span, rt_changes, rt_changes / span, pos_changes, pos_changes / span))


if __name__ == "__main__":
    main()

"""Measure actual GL filter choices during a stationary gameplay yaw sweep.

Run via tools/seam_run.ps1 with -Env PSX_GL_FILTER_CENSUS=1 -Slot 0 -NoCensus
-CpuMode -Py 'tools/filter_census.py --out logs/filter-census.json'.
The runtime trace is bounded, opt-in and writes one line per frame. Counts
are triangle submissions before crack-fill copies or widescreen mirroring.
"""
import argparse
import json
from pathlib import Path
import re
import time

from ask import ask


def q(cmd, **args):
    result = ask(4624, json.dumps({'cmd': cmd, **args}), timeout=15, tries=2)
    if result.get('error') or result.get('ok') is False:
        raise RuntimeError(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('logs/filter-census.json'))
    args = parser.parse_args()
    log = Path('logs/offscreen.err')
    q('clear_input')
    initial = q('read_ram', addr='0x80077624', len=1)['hex']
    start = log.stat().st_size
    checked = 0
    try:
        for yaw in range(256):
            q('write_ram', addr='0x80077624', val=f'{yaw:02X}')
            time.sleep(0.055)
            actual = int(q('read_ram', addr='0x80077624', len=1)['hex'], 16)
            if actual != yaw:
                raise RuntimeError('Camera is not stationary; cannot measure a controlled sweep.')
            checked += 1
        time.sleep(0.1)
        stats = q('dirty_ram_stats')
    finally:
        q('write_ram', addr='0x80077624', val=initial)
        q('clear_input')
    trace = log.read_bytes()[start:].decode(errors='replace')
    pattern = r'filter_census frame=(\d+) flat=(\d+),(\d+),(\d+) shaded=(\d+),(\d+),(\d+) rect=(\d+),(\d+),(\d+) missing=(\d+) aligned=(\d+)'
    rows = [list(map(int, m)) for m in re.findall(pattern, trace)]
    if not rows:
        raise RuntimeError('No filter trace; enable PSX_GL_FILTER_CENSUS=1.')
    totals = [sum(r[i] for r in rows) for i in range(1, 12)]
    result = {'angles': checked, 'frames': len(rows),
              'flat_nearest_bilinear_xbr': totals[0:3],
              'shaded_nearest_bilinear_xbr': totals[3:6],
              'rect_nearest_bilinear_xbr': totals[6:9],
              'shaded_xbr_missing_position': totals[9],
              'shaded_xbr_axis_aligned': totals[10],
              'interpreter_blocks': stats['blocks_run'],
              'interpreter_instructions': stats['insns_run']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'summary': result, 'frames': rows}, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()

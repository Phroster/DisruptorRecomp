"""Inspect sky rectangles in a loaded savestate; optional full camera-yaw sweep.

Run through tools/seam_run.ps1 so the renderer is off-screen and the card is
guarded. Only transient camera yaw is changed; no state or card is saved.
Example: -Slot 0 -NoCensus -Py 'tools/sky_probe.py --out logs/sky-after --sweep'
"""
import argparse
import json
from pathlib import Path
import time

from ask import ask


def q(cmd, **args):
    result = ask(4624, json.dumps({'cmd': cmd, **args}), timeout=15, tries=2)
    if result.get('error') or result.get('ok') is False:
        raise RuntimeError(result)
    return result


def snapshot():
    span = q('gpu_ring_stats')
    result = q('gpu_frame_dump', frame=span['newest_frame']-1, count=8192)
    rects = []
    for e in result['entries']:
        if int(e['op'], 0) != 0x64:
            continue
        w = [int(v, 0) for v in e['w']]
        x, y = w[1] & 0xFFFF, w[1] >> 16
        if x >= 32768: x -= 65536
        if y >= 32768: y -= 65536
        rects.append({'x': x, 'y': y, 'w': w[3] & 0xFFFF, 'h': w[3] >> 16,
                      'u': w[2] & 255, 'v': (w[2] >> 8) & 255,
                      'clut': w[2] >> 16, 'colour': w[0] & 0xFFFFFF,
                      'ot': e['ot'], 'src': e['src']})
    yaw = q('read_ram', addr='0x80077624', len=1)['hex']
    return {'frame': result['frame'], 'yaw': int(yaw, 16), 'rects': rects}


def screenshot(path):
    previous = q('present_shot_seq')['seq']
    q('present_shot', path=str(path.resolve()))
    for _ in range(60):
        result = q('present_shot_seq')
        if result['seq'] != previous:
            assert result['wrote'], result
            return
        time.sleep(0.1)
    raise RuntimeError('present capture timed out')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('logs/sky-probe'))
    parser.add_argument('--sweep', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    q('clear_input')
    time.sleep(2)
    initial = snapshot()
    screenshot(args.out / 'initial.png')
    records = [initial]
    try:
        if args.sweep:
            for yaw in (0, 1, 2, 4, 8, 16, 32, 64, 96, 128, 160, 192, 224, 240, 248, 252, 254, 255):
                q('write_ram', addr='0x80077624', val=f'{yaw:02X}')
                time.sleep(0.25)
                record = snapshot()
                if record['yaw'] != yaw or record['frame'] <= records[-1]['frame']:
                    raise RuntimeError('View did not settle at the requested yaw; use a stationary gameplay save.')
                record['requested_yaw'] = yaw
                records.append(record)
                if yaw in (0, 1, 128, 254, 255):
                    screenshot(args.out / f'yaw-{yaw}.png')
        stats = q('dirty_ram_stats')
        (args.out / 'rectangles.json').write_text(json.dumps(records, indent=2))
        (args.out / 'interpreter.json').write_text(json.dumps(stats, indent=2))
        spans = [r for frame in records for r in frame['rects'] if r['colour'] == 0x808080]
        print(json.dumps({'samples': len(records), 'textured_rectangles': len(spans),
                          'leftmost': min((r['x'] for r in spans), default=None),
                          'rightmost': max((r['x']+r['w'] for r in spans), default=None),
                          'left_margin_rects': sum(r['x'] < 0 for r in spans),
                          'right_margin_rects': sum(r['x']+r['w'] > 320 for r in spans),
                          'interpreter_blocks': stats['blocks_run'],
                          'interpreter_instructions': stats['insns_run']}))
    finally:
        q('write_ram', addr='0x80077624', val=f"{initial['yaw']:02X}")
        q('clear_input')


if __name__ == '__main__':
    main()

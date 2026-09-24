"""Capture the three live Psy-Q kernel call gates without pressing menu buttons.

The periodic collector can miss the short C0 gate even after it executed during
boot. Record the observed A0/B0/C0 instructions explicitly, from current RAM, so
all three entries are compiled after a configuration/cache-key change.
"""
import argparse
import base64
import json
from pathlib import Path
import struct

from ask import ask


def page():
    chunks = []
    for offset in range(0, 4100, 512):
        response = ask(4624, json.dumps({'cmd': 'read_ram', 'addr': f'0x{0x80000000+offset:08X}',
                                        'len': min(512, 4100-offset)}), timeout=10, tries=2)
        if not response.get('ok'):
            raise RuntimeError(response)
        chunks.append(bytes.fromhex(response['hex']))
    return b''.join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('build/overlay_captures_gates.json'))
    args = parser.parse_args()
    first, second = page(), page()
    for offset in (0xA0, 0xB0, 0xC0):
        gate = first[offset:offset+12]
        assert gate == second[offset:offset+12], 'gate changed during capture'
        load, jump, delay = struct.unpack('<III', gate)
        # addiu t0,zero,<kernel routine>; jr t0; nop, as read from this game.
        assert load >> 16 == 0x2408 and jump == 0x01000008 and delay == 0, hex(offset)
    entries = [f'0x{0x80000000+x:08X}' for x in (0xA0, 0xB0, 0xC0)]
    record = {'schema': 'psxrecomp overlay capture v2', 'load_addr': '0x80000000',
              'size': 4100, 'guard_bytes': 4, 'bytes_b64': base64.b64encode(first).decode(),
              'dispatch_entry_pcs': entries, 'function_entry_pcs': entries, 'seeds': entries,
              'executed_pcs': [f'0x{0x80000000+x+i:08X}' for x in (0xA0, 0xB0, 0xC0)
                               for i in (0, 4, 8)]}
    args.out.write_text(json.dumps([record]))
    print('Captured live A0/B0/C0 kernel gates.')


if __name__ == '__main__':
    main()

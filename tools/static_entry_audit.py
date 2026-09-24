#!/usr/bin/env python3
"""Static audit: can any control transfer in the game land somewhere that has
no native entry (and would therefore fall to the dirty-RAM interpreter)?

Usage: python tools/static_entry_audit.py        (run from the project root,
       after build.ps1 has generated generated/SLUS_002.24_*)

Checks, against the generated dispatch table and range manifest:
  1. functions emitted as psx_unknown_dispatch stubs that lie in real code
  2. every register-indirect `jr` in real code, by class:
       - compiler switch tables: every table target needs a native entry
       - BIOS call stubs (li $t2,0xA0/0xB0/0xC0 ; jr $t2): kernel gates
       - return through a copied $ra: reported, target is a return point
       - anything else: listed for manual review with its known target set
  3. every code pointer stored in data or built with lui+addiu/ori
  4. every direct jal target and every cross-function j target
Exit code 0 = no gaps found.
"""
import bisect
import collections
import glob
import re
import struct
import sys

EXE = 'input/SLUS_002.24'
LOAD, TSIZE = 0x80010000, 0x61800
# Hand-verified computed-goto sites (see seeds/functions_extra.txt): site -> targets
KNOWN_COMPUTED = {
    0x80045E54: [0x80045E5C + n * 0x80 for n in range(4)],
    0x80046068: [0x800460AC + n * 0x20 for n in range(4)],
    0x8004607C: [0x800460AC + n * 0x20 for n in range(4)],
    0x80046090: [0x800460AC + n * 0x20 for n in range(4)],
    0x800460A4: [0x800460AC + n * 0x20 for n in range(4)],
}

text = open(EXE, 'rb').read()[0x800:0x800 + TSIZE]


def word(a):
    return struct.unpack_from('<I', text, a - LOAD)[0]


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def main():
    disp = open('generated/SLUS_002.24_dispatch.c').read()
    tbl = disp[disp.index('k_psx_game_dispatch[] = {'):disp.index('k_psx_game_dispatch_index')]
    entries = set(int(m.group(1), 16) for m in
                  re.finditer(r'\{0x([0-9A-F]{8})u, 0x[0-9A-F]{8}u, \d+u, \d+u, ', tbl))
    funcs = sorted(int(l.split()[1], 16) for l in open('generated/SLUS_002.24_full.ranges')
                   if l.startswith('F '))

    # Real code = from the first page to the last page dense in `jr $ra`.
    pages = collections.Counter()
    for off in range(0, TSIZE, 4):
        if struct.unpack_from('<I', text, off)[0] == 0x03E00008:
            pages[(LOAD + off) >> 12] += 1
    dense = [p for p, n in pages.items() if n >= 3]
    code_lo, code_hi = min(dense) << 12, (max(dense) + 1) << 12
    # the image starts with rodata; code begins at the first emitted function
    # that actually contains a return (leaf functions have no stack frame)
    code_lo = next(f for f, nxt in zip(funcs, funcs[1:])
                   if any(word(a) == 0x03E00008 for a in range(f, min(nxt, code_hi), 4)))
    # trim code_hi back to the last jr $ra / jr stub in that page
    last = max(a for a in range(code_lo, code_hi, 4)
               if word(a) == 0x03E00008 or (word(a) >> 26 == 0 and word(a) & 0x3F == 8
                                            and (word(a) >> 21) & 31 == 10))
    code_hi = last + 8
    print('native entries: %d | functions: %d | real code: 0x%08X..0x%08X'
          % (len(entries), len(funcs), code_lo, code_hi))
    problems = []

    # 1. untranslated stubs in real code
    stubs = []
    for path in glob.glob('generated/SLUS_002.24_full_*.c'):
        src = open(path).read()
        stubs += [int(m.group(1), 16) for m in re.finditer(
            r'void func_([0-9A-F]{8})\(CPUState\* cpu\)\s*\{\s*psx_unknown_dispatch', src)]
    real_stubs = [s for s in stubs if code_lo <= s < code_hi]
    print('1. untranslated stub functions: %d total, %d in real code' % (len(stubs), len(real_stubs)))
    problems += [('stub in real code', s) for s in real_stubs]

    # 2. register-indirect jr sites
    klass = collections.Counter()
    for a in range(code_lo, code_hi, 4):
        w = word(a)
        if (w >> 26) != 0 or (w & 0x3F) != 8:
            continue
        r = (w >> 21) & 31
        if r == 31:
            continue
        back = [word(a - 4 * i) for i in range(1, 13) if a - 4 * i >= LOAD]
        near = back[:3] + [word(a + 4)]
        if a in KNOWN_COMPUTED:
            klass['computed-goto (hand-verified)'] += 1
            problems += [('computed goto target', t) for t in KNOWN_COMPUTED[a] if t not in entries]
            continue
        if any((x >> 26) in (9, 13) and ((x >> 21) & 31) == 0 and ((x >> 16) & 31) == r
               and (x & 0xFFFF) in (0xA0, 0xB0, 0xC0) for x in near):
            klass['bios-gate stub'] += 1
            continue
        if any((x >> 26) == 0 and (x & 0x7FF) in (0x20, 0x21, 0x25) and ((x >> 11) & 31) == r
               and 31 in (((x >> 21) & 31), ((x >> 16) & 31)) for x in back[:2]):
            klass['return via copied $ra'] += 1
            continue
        tblbase = None
        for i, x in enumerate(back[:6]):
            if (x >> 26) == 0x23 and ((x >> 16) & 31) == r:
                for y in back[i + 1:]:
                    if (y >> 26) == 0x0F:
                        tblbase = (((y & 0xFFFF) << 16) + s16(x & 0xFFFF)) & 0xFFFFFFFF
                        break
                break
        if tblbase is None:
            klass['UNCLASSIFIED'] += 1
            problems.append(('unclassified jr', a))
            continue
        klass['switch table'] += 1
        t, n = tblbase, 0
        while LOAD <= t < LOAD + TSIZE - 4:
            v = word(t)
            if not (code_lo <= v < code_hi and v % 4 == 0 and abs(v - a) < 0x4000):
                break
            if v not in entries:
                problems.append(('switch target (jr@%08X)' % a, v))
            t += 4
            n += 1
        if n == 0:
            problems.append(('switch table not resolved', a))
    print('2. indirect jr sites:', dict(klass))

    # 3. code pointers
    ptrs = {}
    for lo, hi in ((LOAD, code_lo), (code_hi, LOAD + TSIZE)):
        for a in range(lo, hi - 3, 4):
            v = word(a)
            if code_lo <= v < code_hi and v % 4 == 0:
                ptrs.setdefault(v, a)
    for a in range(code_lo, code_hi, 4):
        w = word(a)
        if (w >> 26) != 0x0F:
            continue
        rt, hi16 = (w >> 16) & 31, (w & 0xFFFF) << 16
        for b in range(a + 4, min(a + 36, code_hi), 4):
            w2 = word(b)
            op = w2 >> 26
            if op in (9, 13) and ((w2 >> 21) & 31) == rt:
                v = (hi16 + (s16(w2 & 0xFFFF) if op == 9 else (w2 & 0xFFFF))) & 0xFFFFFFFF
                if code_lo <= v < code_hi and v % 4 == 0:
                    ptrs.setdefault(v, a)
                break
            if op == 0x0F and ((w2 >> 16) & 31) == rt:
                break

    def is_data_island(v):
        # a pointer into padding/zero words between functions is a data buffer
        return all(word(v + 4 * i) == 0 for i in range(4))
    bad = [v for v in ptrs if v not in entries and not is_data_island(v)]
    print('3. code pointers: %d distinct, %d without a native entry' % (len(ptrs), len(bad)))
    problems += [('code pointer (ref @%08X)' % ptrs[v], v) for v in bad]

    # 4. direct transfers
    starts = funcs

    def owner(a):
        return starts[bisect.bisect_right(starts, a) - 1]
    jal_bad, j_bad, njal, nj = [], [], set(), set()
    for a in range(code_lo, code_hi, 4):
        w = word(a)
        op = w >> 26
        if op not in (2, 3):
            continue
        t = 0x80000000 | ((w & 0x3FFFFFF) << 2)
        if op == 3:
            njal.add(t)
            if t not in entries:
                jal_bad.append(t)
        elif owner(t) != owner(a):
            nj.add(t)
            if t not in entries:
                j_bad.append(t)
    print('4. direct jal targets: %d (%d without entry) | cross-function j targets: %d (%d without entry)'
          % (len(njal), len(set(jal_bad)), len(nj), len(set(j_bad))))
    problems += [('jal target', t) for t in sorted(set(jal_bad))]
    problems += [('j target', t) for t in sorted(set(j_bad))]

    if problems:
        print('GAPS FOUND:')
        for what, a in problems:
            print('   %-34s 0x%08X' % (what, a))
        return 1
    print('No gaps: every statically visible control transfer lands on a native entry.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

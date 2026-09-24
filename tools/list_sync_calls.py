#!/usr/bin/env python3
"""List CPS calls to the frame-sync util 0x8004B3D4 with call-site address,
caller function, and the a0 argument set before the call."""
import glob
import io
import re

TARGET = "0x8004B3D4u"
call_re = re.compile(r'cpu->gpr\[31\] = 0x([0-9A-F]{8})u;.*jal link')


def main():
    rows = []
    for f in sorted(glob.glob("generated/SLUS_002.24_full_*.c")):
        lines = io.open(f, encoding="utf-8", errors="replace").read().splitlines()
        for i, l in enumerate(lines):
            if TARGET in l and "cpu->pc = " + TARGET in l:
                # find call site ra = the gpr[31] assignment above
                ra = None
                for j in range(i, max(0, i - 12), -1):
                    m = re.search(r'cpu->gpr\[31\] = 0x([0-9A-F]{8})u', lines[j])
                    if m:
                        ra = int(m.group(1), 16)
                        break
                site = (ra - 8) if ra else None
                # find containing function
                fn = None
                for j in range(i, 0, -1):
                    if lines[j].startswith("void func_") or lines[j].startswith("static void func_"):
                        fn = lines[j][:40]
                        break
                # look back for a0 assignment within 20 lines
                a0 = None
                for j in range(max(0, i - 40), i):
                    m = re.search(r'cpu->gpr\[4\] = ([^;]+);', lines[j])
                    if m:
                        a0 = m.group(1)[:40]
                rows.append((fn, site, a0, f.split("\\")[-1]))
    for fn, site, a0, f in rows:
        print("%-38s site=0x%08X a0=%-28s %s" % (fn, site or 0, a0 or "?", f))


if __name__ == "__main__":
    main()

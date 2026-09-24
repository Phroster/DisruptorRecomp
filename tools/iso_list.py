#!/usr/bin/env python3
"""List (and optionally extract) files from the raw MODE2/2352 image.

Usage:
  python tools/iso_list.py                       # full listing
  python tools/iso_list.py --grep WAD            # filter paths
  python tools/iso_list.py --extract /WAD.IN;1 out.bin
"""
import struct
import sys

BIN = "disc/Disruptor.bin"
SEC = 2352
DATA_OFF = 24
DATA_LEN = 2048


def read_sector(lba):
    with open(BIN, "rb") as f:
        f.seek(lba * SEC + DATA_OFF)
        return f.read(DATA_LEN)


def walk(extent_lba, size):
    """Yield (name, is_dir, extent_lba, data_size) for one directory extent."""
    data = b""
    left = size
    lba = extent_lba
    while left > 0:
        data += read_sector(lba)
        lba += 1
        left -= DATA_LEN
    off = 0
    while off < len(data):
        rec_len = data[off]
        if rec_len == 0:
            break
        rec = data[off:off + rec_len]
        if len(rec) < 33:
            break
        extent = struct.unpack_from("<I", rec, 2)[0]
        dsize = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        name = rec[33:33 + name_len]
        if name_len == 1:
            nm = chr(name[0])
        else:
            nm = name.decode("ascii", "replace")
        if nm not in ("\x00", "\x01"):
            yield nm, bool(flags & 2), extent, dsize
        off += rec_len


def main():
    pvd = read_sector(16)
    if pvd[1:6] != b"CD001":
        sys.exit("not an ISO9660 PVD at LBA 16")
    root_extent = struct.unpack_from("<I", pvd, 156 + 2)[0]
    root_size = struct.unpack_from("<I", pvd, 156 + 10)[0]
    print("volume:", pvd[40:72].decode("ascii", "replace").strip())

    entries = []

    def rec(dpath, lba, size):
        for nm, is_dir, ex, ds in walk(lba, size):
            p = dpath + "/" + nm
            if is_dir:
                rec(p, ex, ds)
            else:
                entries.append((p, ex, ds))

    rec("", root_extent, root_size)

    args = sys.argv[1:]
    grep = None
    if args and args[0] == "--grep":
        grep = args[1].upper()
    if args and args[0] == "--extract":
        target = args[1].upper()
        out = args[2]
        for p, ex, ds in entries:
            if p.upper() == target:
                with open(out, "wb") as f:
                    left, lba = ds, ex
                    while left > 0:
                        chunk = read_sector(lba)[:min(DATA_LEN, left)]
                        f.write(chunk)
                        left -= len(chunk)
                        lba += 1
                print("extracted", p, ds, "bytes ->", out)
                return
        sys.exit("not found: " + target)

    files = [e for e in entries if grep is None or grep in e[0].upper()]
    files.sort(key=lambda e: -e[2])
    print("%d files (of %d total)" % (len(files), len(entries)))
    for p, ex, ds in files:
        print("  %10d  lba %6d  %s" % (ds, ex, p))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""What changes across the border between two neighbouring terrain quads?

Usage: python tools/quad_edge_census.py [--view still]

For one render pass of the running GL build (static view - do not hold input):
  1. the GPU seam census gives every textured gouraud quad (GP0 0x3C) and the
     RAM address of its packet;
  2. the packets are read back from guest RAM (colours, vertices, uv, CLUT,
     texture page) and VRAM is dumped, so every quad's texels can be decoded;
  3. for every edge shared by two quads, 16 points along the edge are evaluated
     on BOTH sides: texel colour, vertex lighting, and their product (what is
     drawn).
Reported per channel on the 0..255 scale, averaged over all shared edges:
  drawn      |A - B| of the final colour across the border (the visible jump)
  texture    the same with lighting removed (pure texture content mismatch)
  lighting   the same with texture removed (pure lighting step)
  inside     |row - next row| one texel inside a quad, same direction: how much
             the picture changes over one texel where there is NO border. A
             border is only visible when "drawn" is clearly larger than this.
Also: how many shared edges join two quads that use the same tile.
"""
import collections
import csv
import json
import os
import sys
import time

from ask import ask

PORT = 4624
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def q(**k):
    return ask(PORT, json.dumps(k), timeout=30.0, tries=2)


def read_words(addr, n):
    r = q(cmd="read_ram", addr="0x%08X" % (0x80000000 | addr), len=n * 4)
    hx = r.get("hex") or r.get("data") or ""
    raw = bytes.fromhex(hx)
    return [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw) - 3, 4)]


def dump_vram():
    vram = [[0] * 1024 for _ in range(512)]
    for by in range(0, 512, 128):
        for bx in range(0, 1024, 128):
            r = q(cmd="vram_peek", x=bx, y=by, w=128, h=128)
            hx = r["hex"]
            for row in range(128):
                base = row * 128 * 4
                line = vram[by + row]
                for col in range(128):
                    line[bx + col] = int(hx[base + col * 4: base + col * 4 + 4], 16)
    return vram


class Quad:
    def __init__(self, words):
        self.cmd = words[0] >> 24
        self.col = [words[i] & 0xFFFFFF for i in (0, 3, 6, 9)]
        self.vw = [words[i] & 0x07FF07FF for i in (1, 4, 7, 10)]
        self.uv = [((words[i] & 0xFF), ((words[i] >> 8) & 0xFF)) for i in (2, 5, 8, 11)]
        clut = (words[2] >> 16) & 0xFFFF
        self.clut = ((clut & 0x3F) * 16, (clut >> 6) & 0x1FF)
        tp = (words[5] >> 16) & 0x1FF
        self.tpx, self.tpy, self.depth = (tp & 0xF) * 64, ((tp >> 4) & 1) * 256, min(2, (tp >> 7) & 3)
        self.tile = (self.tpx, self.tpy, self.clut, tuple(sorted(self.uv)))

    def texel(self, vram, u, v):
        u, v = int(u) & 255, int(v) & 255
        if self.depth == 0:
            px = vram[(self.tpy + v) & 511][(self.tpx + (u >> 2)) & 1023]
            raw = vram[self.clut[1]][(self.clut[0] + ((px >> ((u & 3) * 4)) & 0xF)) & 1023]
        elif self.depth == 1:
            px = vram[(self.tpy + v) & 511][(self.tpx + (u >> 1)) & 1023]
            raw = vram[self.clut[1]][(self.clut[0] + ((px >> ((u & 1) * 8)) & 0xFF)) & 1023]
        else:
            raw = vram[(self.tpy + v) & 511][(self.tpx + u) & 1023]
        return [((raw >> s) & 31) * 255.0 / 31.0 for s in (0, 5, 10)]


EDGES = ((0, 1), (1, 3), (3, 2), (2, 0))      # PS1 quad vertex order is a Z
OPPOSITE = {(0, 1): (2, 3), (1, 3): (0, 2), (3, 2): (1, 0), (2, 0): (3, 1)}


def lerp(a, b, t):
    return [a[i] + (b[i] - a[i]) * t for i in range(len(a))]


def rgb_of(c):
    return [(c >> s) & 255 for s in (0, 8, 16)]


def side(quad, vram, ia, ib, t, inward):
    """Colour pieces of `quad` at parameter t along edge ia->ib, `inward` texels inside."""
    oa, ob = OPPOSITE[(ia, ib)] if (ia, ib) in OPPOSITE else OPPOSITE[(ib, ia)][::-1]
    uv_e = lerp(quad.uv[ia], quad.uv[ib], t)
    uv_o = lerp(quad.uv[oa], quad.uv[ob], t)
    d = [uv_o[0] - uv_e[0], uv_o[1] - uv_e[1]]
    n = max(1e-6, (d[0] ** 2 + d[1] ** 2) ** 0.5)
    # sample the centre of the first / second texel row inside the quad
    uv = [uv_e[0] + d[0] / n * (0.5 + inward), uv_e[1] + d[1] / n * (0.5 + inward)]
    tex = quad.texel(vram, uv[0], uv[1])
    light = lerp(rgb_of(quad.col[ia]), rgb_of(quad.col[ib]), t)
    drawn = [min(255.0, tex[i] * light[i] / 128.0) for i in range(3)]
    return tex, light, drawn


def mad(a, b):
    return sum(abs(a[i] - b[i]) for i in range(3)) / 3.0


def main():
    path = os.path.join(ROOT, "logs", "seam_frame.csv").replace(os.sep, "/")
    q(cmd="clear_input")
    q(cmd="seam_dump", path=path)
    time.sleep(1.0)
    q(cmd="seam_dump", path=path)
    rows = list(csv.DictReader(open(path, newline="")))
    bases = []
    for i in range(0, len(rows) - 2, 3):
        if int(rows[i]["prim"]) == 0x3C:
            a = int(rows[i]["addr"], 16)
            if a != 0xFFFFFFFF:
                bases.append((a - 4) & 0x1FFFFC)       # first triangle's first vertex = packet word 1
    bases = sorted(set(bases))
    quads = []
    for b in bases:
        w = read_words(b, 12)
        if len(w) == 12 and (w[0] >> 24) == 0x3C:
            quads.append(Quad(w))
    print("textured gouraud quads in the pass: %d (packets read back: %d)" % (len(bases), len(quads)))
    vram = dump_vram()

    edge_users = collections.defaultdict(list)
    for qi, quad in enumerate(quads):
        for ia, ib in EDGES:
            key = tuple(sorted((quad.vw[ia], quad.vw[ib])))
            if key[0] != key[1]:
                edge_users[key].append((qi, ia, ib))
    shared = [u for u in edge_users.values() if len(u) == 2 and u[0][0] != u[1][0]]
    tot = collections.Counter()
    same_tile = 0
    n = 0
    for (qa, a0, a1), (qb, b0, b1) in shared:
        A, B = quads[qa], quads[qb]
        flip = A.vw[a0] != B.vw[b0]
        same_tile += A.tile == B.tile
        for k in range(16):
            t = (k + 0.5) / 16.0
            ta, la, da = side(A, vram, a0, a1, t, 0)
            tb, lb, db = side(B, vram, b0, b1, 1.0 - t if flip else t, 0)
            ta2, la2, da2 = side(A, vram, a0, a1, t, 1)
            tot["drawn"] += mad(da, db)
            tot["texture"] += mad(ta, tb)
            tot["lighting"] += mad(la, lb)
            tot["inside"] += mad(da, da2)
            n += 1
    n = max(1, n)
    print("edges shared by two quads: %d | joining two quads with the SAME tile: %d (%.0f%%)" % (
        len(shared), same_tile, 100.0 * same_tile / max(1, len(shared))))
    print("mean absolute difference per channel (0..255):")
    for k in ("drawn", "texture", "lighting", "inside"):
        print("   %-9s %6.1f" % (k, tot[k] / n))
    tiles = collections.Counter(qd.tile for qd in quads)
    sizes = collections.Counter((max(u for u, v in qd.uv) - min(u for u, v in qd.uv) + 1,
                                 max(v for u, v in qd.uv) - min(v for u, v in qd.uv) + 1) for qd in quads)
    print("distinct tiles: %d | tile sizes (texels): %s" % (len(tiles), dict(sizes.most_common(5))))


if __name__ == "__main__":
    main()

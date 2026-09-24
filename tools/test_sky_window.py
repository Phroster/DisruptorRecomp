"""Execute the disc's sky clipping/wrap instructions with the configured patches.

Checks MIPS branch/load delay slots, off-screen rejection, near-plane defaults,
unchanged central projection, and panorama phase across the negative-X reveal.
Requires the locally extracted executable. Does not run the game or touch saves.
"""
from pathlib import Path
import struct
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASE, SP, END = 0x80010000, 0x801FE000, 0x8003B6AC


def signed(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


class Machine:
    """Small instruction executor for the two measured blocks, not game emulation."""
    def __init__(self, image, patches):
        self.image, self.patches = image, patches
        self.r = [0] * 32
        self.r[29] = SP
        self.mem = {}
        self.hi = self.lo = 0
        self.load = None
        self.target = None

    def read(self, addr, n):
        raw = bytes(self.mem.get(addr+i, self.image[addr+i-BASE+2048]
                    if BASE <= addr+i < BASE+len(self.image)-2048 else 0)
                    for i in range(n))
        return int.from_bytes(raw, 'little')

    def write(self, addr, value):
        for i, byte in enumerate((value & 0xFFFFFFFF).to_bytes(4, 'little')):
            self.mem[addr+i] = byte

    def run(self, pc, stops):
        for _ in range(200):
            if pc in stops:
                return pc
            w = self.patches.get(pc)
            if w is None:
                w = struct.unpack_from('<I', self.image, pc-BASE+2048)[0]
            op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
            shift, fn, uimm = (w >> 6) & 31, w & 63, w & 0xFFFF
            imm = uimm - 0x10000 if uimm & 0x8000 else uimm
            a, b = self.r[rs], self.r[rt]
            old_load, old_target = self.load, self.target
            self.load = self.target = None
            written = set()

            def put(reg, value):
                if reg:
                    self.r[reg] = value & 0xFFFFFFFF
                    written.add(reg)

            if op == 0:
                if fn == 0: put(rd, b << shift)
                elif fn == 2: put(rd, b >> shift)
                elif fn == 3: put(rd, signed(b) >> shift)
                elif fn == 16: put(rd, self.hi)
                elif fn == 18: put(rd, self.lo)
                elif fn == 24:
                    product = signed(a) * signed(b)
                    self.lo, self.hi = product & 0xFFFFFFFF, (product >> 32) & 0xFFFFFFFF
                elif fn == 26:
                    assert signed(b) != 0
                    q = abs(signed(a)) // abs(signed(b))
                    if (signed(a) < 0) != (signed(b) < 0): q = -q
                    self.lo, self.hi = q & 0xFFFFFFFF, (signed(a)-q*signed(b)) & 0xFFFFFFFF
                elif fn == 33: put(rd, a+b)
                elif fn == 35: put(rd, a-b)
                elif fn == 39: put(rd, ~(a | b))
                elif fn == 42: put(rd, int(signed(a) < signed(b)))
                else: raise AssertionError(f'unsupported SPECIAL {w:08x} at {pc:08x}')
            elif op in (1, 4, 5, 6):
                if op == 1:
                    assert rt in (0, 1)
                    take = signed(a) >= 0 if rt == 1 else signed(a) < 0
                elif op == 4: take = a == b
                elif op == 5: take = a != b
                else: take = signed(a) <= 0
                self.target = pc + 4 + 4*imm if take else pc + 8
            elif op == 2: self.target = ((pc+4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
            elif op == 9: put(rt, a+imm)
            elif op == 10: put(rt, int(signed(a) < imm))
            elif op == 12: put(rt, a & uimm)
            elif op == 13: put(rt, a | uimm)
            elif op == 15: put(rt, uimm << 16)
            elif op in (35, 37): self.load = (rt, self.read((a+imm) & 0xFFFFFFFF, 4 if op == 35 else 2))
            elif op == 43: self.write((a+imm) & 0xFFFFFFFF, b)
            else: raise AssertionError(f'unsupported instruction {w:08x} at {pc:08x}')
            if old_load and old_load[0] not in written:
                put(*old_load)
            pc = old_target if old_target is not None else pc+4
        raise AssertionError('instruction block did not terminate')


def main():
    image = (ROOT / 'input/SLUS_002.24').read_bytes()
    cfg = tomllib.loads((ROOT / 'game.toml').read_text())
    patches = {}
    for p in cfg['recompiler']['patch']:
        if not p['id'].startswith('ws-sky-'):
            continue
        pc = int(p['address'], 0)
        assert struct.unpack_from('<I', image, pc-BASE+2048)[0] == int(p['expected'], 0)
        patches[pc] = int(p['replacement'], 0)
    assert len(patches) == 26

    def project(x, z):
        reciprocal = int.from_bytes(image[0x80057E98-BASE+2048+2*z:0x80057E98-BASE+2050+2*z], 'little')
        return (((x*5) >> 1)*reciprocal >> 10) + 160

    # Check stock and wide clipping against independent geometric bounds.
    coords = (-8192, -4096, -1024, -512, -64, -1, 0, 1, 64, 512, 1024, 4096, 8192)
    count = 0
    for mods, xmin, xmax in (({}, 0, 320), (patches, -64, 384)):
        for zl in (0, 7, 8, 31, 512, 4095):
            for zr in (0, 7, 8, 31, 512, 4095):
                for xl in coords:
                    for xr in coords:
                        m = Machine(image, mods)
                        m.r[25] = (-64) & 0xFFFFFFFF
                        m.r[6], m.r[5], m.r[10], m.r[11] = zl, zr, xl & 0xFFFFFFFF, xr & 0xFFFFFFFF
                        l = project(xl, zl) if zl >= 8 else xmin
                        r = project(xr, zr) if zr >= 8 else xmax
                        rejected = l >= xmax or r <= xmin
                        stop = m.run(0x8003B214, {0x8003B328, END})
                        assert (stop == END) == rejected, (xmin, zl, zr, xl, xr, l, r, hex(stop))
                        if not rejected:
                            actual = signed(m.read(SP+0x40, 4)), signed(m.read(SP+0x28, 4))
                            assert actual == (max(xmin, l), min(xmax, r)), (xmin, actual, l, r)
                        count += 1

    # The full-sky path uses the same bounds and retains its original height.
    m = Machine(image, patches)
    m.r[5] = 120
    m.run(0x8003AFE0, {0x8003B328, END})
    assert (signed(m.read(SP+0x40, 4)), m.read(SP+0x28, 4), m.read(SP+0x48, 4)) == (-64, 384, 120)

    # Every yaw and every possible left edge: preserve texture phase and width,
    # including negative starts and spans straddling the end of the panorama.
    wraps = 0
    for yaw in range(256):
        for left in range(-64, 384):
            m = Machine(image, patches)
            m.r[14] = yaw
            m.write(SP+0x40, left)
            m.write(SP+0x28, 384)
            m.run(0x8003B328, {0x8003B390})
            start, end = m.read(SP+0x18, 4), m.read(SP+0x28, 4)
            assert start == (left+(255-yaw)*5) % 1280
            assert end-start == 384-left
            assert m.read(SP+0x20, 4) == end
            assert signed(m.read(SP+0x38, 4)) == left
            wraps += 1
    print(f'Sky window: {count} clipping cases, full-sky bounds and {wraps} panorama wraps passed.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Decode the original MIPS instructions embedded as comments in a generated
recompiled C file, for a given address range.

Usage: python tools/gen_disasm.py <generated.c> <lo> <hi>

The recompiler emits each source instruction as `/* 0xADDR: 0xWORD */`, so
this recovers a listing for code the static analyzer did not model.
"""
import re
import sys

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]

PAT = re.compile(r"/\* 0x([0-9A-Fa-f]{8}): 0x([0-9A-Fa-f]{8}) \*/")

S_RTYPE = {
    0x00: "sll", 0x02: "srl", 0x03: "sra", 0x04: "sllv", 0x06: "srlv",
    0x07: "srav", 0x08: "jr", 0x09: "jalr", 0x10: "mfhi", 0x11: "mthi",
    0x12: "mflo", 0x13: "mtlo", 0x18: "mult", 0x19: "multu", 0x1A: "div",
    0x1B: "divu", 0x20: "add", 0x21: "addu", 0x22: "sub", 0x23: "subu",
    0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor", 0x2A: "slt",
    0x2B: "sltu",
}


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def decode(addr, w):
    op = w >> 26
    rs = (w >> 21) & 31
    rt = (w >> 16) & 31
    rd = (w >> 11) & 31
    sa = (w >> 6) & 31
    imm = w & 0xFFFF
    tgt = (addr & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
    if w == 0:
        return "nop"
    if op == 0x00:
        f = w & 0x3F
        n = S_RTYPE.get(f)
        if not n:
            return None
        if n in ("jr",):
            return f"jr ${REG[rs]}"
        if n in ("jalr",):
            return f"jalr ${REG[rd]}, ${REG[rs]}"
        if n in ("mfhi", "mflo"):
            return f"{n} ${REG[rd]}"
        if n in ("mthi", "mtlo"):
            return f"{n} ${REG[rs]}"
        if n in ("mult", "multu", "div", "divu"):
            return f"{n} ${REG[rs]}, ${REG[rt]}"
        if n in ("sll", "srl", "sra"):
            return f"{n} ${REG[rd]}, ${REG[rt]}, {sa}"
        if n in ("sllv", "srlv", "srav"):
            return f"{n} ${REG[rd]}, ${REG[rt]}, ${REG[rs]}"
        return f"{n} ${REG[rd]}, ${REG[rs]}, ${REG[rt]}"
    if op == 0x01:
        names = {0: "bltz", 1: "bgez", 0x10: "bltzal", 0x11: "bgezal"}
        n = names.get(rt, f"op01:{rt}")
        return f"{n} ${REG[rs]}, {tgt:#x}"
    if op == 0x02:
        return f"j {tgt:#x}"
    if op == 0x03:
        return f"jal {tgt:#x}"
    if op in (0x04, 0x05, 0x06, 0x07):
        n = {4: "beq", 5: "bne", 6: "blez", 7: "bgtz"}[op]
        if op in (6, 7):
            return f"{n} ${REG[rs]}, {tgt:#x}"
        return f"{n} ${REG[rs]}, ${REG[rt]}, {tgt:#x}"
    if op in (0x08, 0x09, 0x0A, 0x0B):
        n = {8: "addi", 9: "addiu", 0xA: "slti", 0xB: "sltiu"}[op]
        return f"{n} ${REG[rt]}, ${REG[rs]}, {s16(imm)}"
    if op == 0x0C:
        return f"andi ${REG[rt]}, ${REG[rs]}, {imm:#x}"
    if op == 0x0D:
        return f"ori ${REG[rt]}, ${REG[rs]}, {imm:#x}"
    if op == 0x0E:
        return f"xori ${REG[rt]}, ${REG[rs]}, {imm:#x}"
    if op == 0x0F:
        return f"lui ${REG[rt]}, {imm:#x}"
    if op == 0x10:
        return f"cop0 ({w & 0x03FFFFFF:#x})"
    if op == 0x12:
        return f"cop2 ({w & 0x03FFFFFF:#x})"
    if op in (0x20, 0x21, 0x23, 0x24, 0x25, 0x26):
        n = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu",
             0x25: "lhu", 0x26: "lwr"}[op]
        return f"{n} ${REG[rt]}, {s16(imm)}(${REG[rs]})"
    if op in (0x28, 0x29, 0x2A, 0x2B, 0x2E):
        n = {0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw",
             0x2E: "swr"}[op]
        return f"{n} ${REG[rt]}, {s16(imm)}(${REG[rs]})"
    return None


def main():
    path, lo, hi = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = PAT.search(line)
            if not m:
                continue
            addr, w = int(m.group(1), 16), int(m.group(2), 16)
            if addr < lo or addr >= hi:
                continue
            text = decode(addr, w)
            out.append((addr, text if text else f"word {w:#010x}"))
    out.sort()
    for addr, text in out:
        print(f"{addr:08X}  {text}")


if __name__ == "__main__":
    main()

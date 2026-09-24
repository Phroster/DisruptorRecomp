#!/usr/bin/env python3
"""Disassemble a guest RAM range by reading it from the debug server.
Usage: mips_ram_disasm.py <port> <hexstart> <hexend>"""
import sys

sys.path.insert(0, "tools")
from input_probe import send

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def dis(w, pc):
    op = w >> 26
    rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    imm = w & 0xFFFF
    tgt = w & 0x03FFFFFF
    if op == 0:
        fn = w & 0x3F
        if fn == 0 and w == 0:
            return "nop"
        names = {0x00: "sll", 0x02: "srl", 0x03: "sra", 0x08: "jr",
                 0x09: "jalr", 0x21: "addu", 0x23: "subu", 0x20: "add",
                 0x2A: "slt", 0x2B: "sltu", 0x18: "mult", 0x19: "multu",
                 0x1A: "div", 0x1B: "divu", 0x10: "mfhi", 0x12: "mflo",
                 0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor"}
        n = names.get(fn, "special_%02X" % fn)
        if fn in (0x00, 0x02, 0x03):
            return "%s %s, %s, %d" % (n, REG[rd], REG[rt], (w >> 6) & 31)
        if fn == 0x08:
            return "jr %s" % REG[rs]
        if fn == 0x09:
            return "jalr %s, %s" % (REG[rd], REG[rs])
        return "%s %s, %s, %s" % (n, REG[rd], REG[rs], REG[rt])
    names = {0x02: "j", 0x03: "jal", 0x04: "beq", 0x05: "bne", 0x06: "blez",
             0x07: "bgtz", 0x08: "addi", 0x09: "addiu", 0x0A: "slti",
             0x0B: "sltiu", 0x0C: "andi", 0x0D: "ori", 0x0E: "xori",
             0x0F: "lui", 0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu",
             0x25: "lhu", 0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x2E: "swr",
             0x2A: "swl", 0x22: "lwl", 0x26: "lwr"}
    n = names.get(op, "op_%02X" % op)
    if op in (0x02, 0x03):
        return "%s 0x%08X" % (n, (pc & 0xF0000000) | (tgt << 2))
    if op == 0x0F:
        return "lui %s, 0x%04X" % (REG[rt], imm)
    if op in (0x04, 0x05):
        return "%s %s, %s, 0x%08X" % (n, REG[rs], REG[rt], pc + 4 + (s16(imm) << 2))
    if op == 0x06 or op == 0x07:
        return "%s %s, 0x%08X" % (n, REG[rs], pc + 4 + (s16(imm) << 2))
    if op in (0x23, 0x20, 0x21, 0x24, 0x25, 0x28, 0x29, 0x2B, 0x22, 0x26, 0x2A, 0x2E):
        return "%s %s, %d(%s)" % (n, REG[rt], s16(imm), REG[rs])
    if op in (0x0C, 0x0D, 0x0E):
        return "%s %s, %s, 0x%04X" % (n, REG[rt], REG[rs], imm)
    if op in (0x08, 0x09, 0x0A, 0x0B):
        return "%s %s, %s, %d" % (n, REG[rt], REG[rs], s16(imm))
    return "%s %s, %s, 0x%04X" % (n, REG[rt], REG[rs], imm)


def main():
    port = int(sys.argv[1])
    lo = int(sys.argv[2], 16)
    hi = int(sys.argv[3], 16)
    n = hi - lo
    raw = bytes.fromhex(send(port, '{"cmd":"read_ram","addr":"0x%X","len":%d}'
                             % (lo, n))["hex"])
    for off in range(0, n, 4):
        w = int.from_bytes(raw[off:off + 4], "little")
        pc = lo + off
        print("0x%08X  %08X  %s" % (pc, w, dis(w, pc)))


if __name__ == "__main__":
    main()

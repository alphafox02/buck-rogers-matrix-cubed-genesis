# SPDX-License-Identifier: MIT
"""
Disassemble the Genesis sound driver.

Music does not run on the 68000. `0x1B5CE` copies 6112 bytes of Z80 code
from ROM `0x19D86` to `0xA00000`, and `0x1B89A` hands it track pointers
through Z80 RAM. The driver is custom -- it signs itself `SHayes1991` -- so
its sequence format is not documented anywhere and has to be read out of
the code.

Addresses printed are Z80 addresses; add DRIVER to get a ROM offset.

Usage:
    z80dump.py <rom> <start> <count>     # both in Z80 address space
"""

import sys
from pathlib import Path

from z80dis import z80

DRIVER = 0x19D86
LENGTH = 0x17E0


def load(rom_path):
    return Path(rom_path).read_bytes()[DRIVER:DRIVER + LENGTH]


def disasm(code, start, count):
    out, pc = [], start
    for _ in range(count):
        if pc >= len(code):
            break
        try:
            ins = z80.disasm(code[pc:pc + 4], pc)
            n = z80.decode(code[pc:pc + 4], pc).len
        except Exception:
            out.append((pc, f"db ${code[pc]:02X}", 1))
            pc += 1
            continue
        out.append((pc, ins, n))
        pc += n
    return out


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    code = load(sys.argv[1])
    start, count = int(sys.argv[2], 0), int(sys.argv[3], 0)
    for pc, ins, n in disasm(code, start, count):
        raw = code[pc:pc + n].hex()
        print(f"  {pc:04X}: {raw:<10} {ins}")

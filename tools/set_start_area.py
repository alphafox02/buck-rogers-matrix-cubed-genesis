"""
Change which area the game boots into.

Block `0x00` is the boot script, and at offset 0x42 it does:

    00042  NEWECL     0x10
    00045  LOADFILES  0x10, 0x7F, 0xFF

`NEWECL` switches the running script to that area's block and `LOADFILES`
loads its map. Rewriting both immediates sends the player somewhere else on
start-up, which is the difference between "the ROM contains a transplanted
area" and "boot the ROM and you are standing in it".

Only the immediate operands change, so the instruction stream keeps its
length and no layout or jump target moves.

Usage:
    set_start_area.py <in.gen> <out.gen> <area_id>
"""

import sys
from pathlib import Path

import expand
import genesis_disasm as G
import genesis_ecl
import integrity


def retarget(code: bytes, area: int) -> bytes:
    """Rewrite the boot block's first NEWECL and LOADFILES to `area`."""
    table = G.load_opcodes()
    found = G.disassemble(code, table)
    out = bytearray(code)
    changed = []
    for off in sorted(found):
        ins = found[off]
        if ins.name not in ("NEWECL", "LOADFILES"):
            continue
        arg = ins.args[0]
        if arg.kind != "imm":
            continue
        # Immediates are a type byte followed by the value; only type 0x00
        # (one byte) is expected here, and rewriting it in place preserves
        # the instruction's length.
        if out[off + 1] != 0x00:
            continue
        changed.append((off, out[off + 2], ins.name))
        out[off + 2] = area
        if len(changed) == 2:
            break
    return bytes(out), changed


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst, area = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3], 0)
    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    ids = [b[0] for b in blocks]
    if area not in ids:
        sys.exit(f"area 0x{area:02X} not present")

    slot = ids.index(0x00)
    code, changed = retarget(blocks[slot][1], area)
    if not changed:
        sys.exit("no NEWECL/LOADFILES with an immediate found in the boot block")
    for off, old, name in changed:
        print(f"  {name} at 0x{off:04X}: 0x{old:02X} -> 0x{area:02X}")
    blocks[slot] = (0x00, code, blocks[slot][2])

    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(expand.read_geo_stream(rom))
    out = builder.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

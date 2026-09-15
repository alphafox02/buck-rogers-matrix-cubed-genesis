"""
Replace area 0x00 with a boot stub that drops the player into a chosen area.

Neither game's area 0x00 is usable as a boot block for a player. Both are
SSI developer harnesses: their movement hooks jump to a warp menu --

    00D0: PRINT_CLEAR      "WHERE DO YOU WISH TO GO?"
    00FA: MENU_HORIZONTAL  [0x7F79], 7      ; JUMP ARENA DUEL SPACE ...

-- so in Matrix Cubed's block 1 every step the player takes opens that menu,
and picking SPACE launches the ship. Countdown's block 0x00 is the same
shape, which is why retargeting one NEWECL inside it did not help: the
branch a player actually takes falls through into the menu.

The stub replaces the whole block with the shortest thing that works,
mirroring the sequence Countdown's own boot uses when it does reach the
game:

    NEWECL     <area>
    LOADFILES  <area>, 0x7F, 0xFF
    LOADPIECES <wallset>
    SAVE       <y>, [0x9AF7]      ; DUNGEON_Y
    SAVE       <x>, [0x9AF6]      ; DUNGEON_X
    SAVE       0,   [0x9AFA]      ; DUNGEON_DIR
    NEWREGION  0, 1, 0, 0, 0xF, 0xF
    EXIT

and points all four event hooks at a bare EXIT, so nothing the player does
can re-enter it.

Usage:
    bootstub.py <in.gen> <out.gen> <area> <wallset> <x> <y>
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

import expand
import genesis_disasm as G
import genesis_ecl
import integrity

DUNGEON_X, DUNGEON_Y, DUNGEON_DIR = 0x9AF6, 0x9AF7, 0x9AFA


def _imm(v):
    if v <= 0xFF:
        return bytes([0x00, v])
    return bytes([0x02]) + struct.pack("<H", v)


def _mem(v):
    return bytes([0x01]) + struct.pack("<H", v & 0xFFFF)


def build(area, wallset, x, y):
    table = G.load_opcodes()
    op = {n: o for o, (n, _) in table.items()}

    # Five hooks, each a GOTO: opcode plus a 3-byte memory operand.
    HOOK = 4
    exit_at = 5 * HOOK
    init_at = exit_at + 1

    out = bytearray()
    for _ in range(4):                       # move / search / rest / ...
        out += bytes([op["GOTO"]]) + _mem(G.CODE_BASE + exit_at)
    out += bytes([op["GOTO"]]) + _mem(G.CODE_BASE + init_at)
    assert len(out) == exit_at
    out += bytes([op["EXIT"]])
    assert len(out) == init_at

    out += bytes([op["NEWECL"]]) + _imm(area)
    out += bytes([op["LOADFILES"]]) + _imm(area) + _imm(0x7F) + _imm(0xFF)
    out += bytes([op["LOADPIECES"]]) + _imm(wallset)
    out += bytes([op["SAVE"]]) + _imm(y) + _mem(DUNGEON_Y)
    out += bytes([op["SAVE"]]) + _imm(x) + _mem(DUNGEON_X)
    out += bytes([op["SAVE"]]) + _imm(0) + _mem(DUNGEON_DIR)
    out += bytes([op["NEWREGION"]]) + b"".join(
        _imm(v) for v in (0, 1, 0, 0, 0x0F, 0x0F))
    out += bytes([op["EXIT"]])
    return bytes(out)


def main():
    if len(sys.argv) < 7:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    area, wallset, x, y = (int(v, 0) for v in sys.argv[3:7])

    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    ids = [b[0] for b in blocks]
    if area not in ids:
        sys.exit(f"area 0x{area:02X} not present")

    code = build(area, wallset, x, y)
    slot = ids.index(0x00)
    print(f"area 0x00 boot stub: {len(blocks[slot][1])} -> {len(code)} bytes, "
          f"entering area 0x{area:02X} at ({x},{y}) with wall set {wallset}")

    # Verify the stub reads back as the instructions it was meant to be.
    table = G.load_opcodes()
    found = G.disassemble(code, table)
    claimed = sum(i.size for i in found.values())
    if claimed != len(code):
        sys.exit(f"stub does not disassemble cleanly: {claimed} of {len(code)} bytes")
    for off in sorted(found):
        print(f"    {off:04X}: {found[off].render()}")

    blocks[slot] = (0x00, code, b"\0")
    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(expand.read_geo_stream(rom))
    out = builder.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

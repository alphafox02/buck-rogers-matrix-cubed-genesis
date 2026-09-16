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
    SAVE       <f>, [0x9AFA]      ; DUNGEON_DIR
    NEWREGION  0, 1, 0, 0, 0xF, 0xF
    EXIT

and points all four event hooks at a bare EXIT, so nothing the player does
can re-enter it.

The engine picks its entry area at 0x04146, and there is more than one:

    04146: tst.b   $ba5a.w
    0414A: beq.b   $4154
    0414C:   move.b #$3, $b9f0.w     ; -> area 0x03
    04154: tst.b   $ca21.w
    04158: bne.b   $4160
    0415A:   clr.b  $b9f0.w          ; -> area 0x00
    04160:   move.b #$10, $b9f0.w    ; -> area 0x10   "default team"
    04168: move.b  $97e8.w, $b9f0.w  ; -> the saved area, on a restore
    04174: bsr.w   $40d0

Choosing "load default team" boots area 0x10, so a stub in 0x00 alone is
never reached. The stub goes into every new-game entry.

The map is named separately from the script, because they are not always
the same. A cutscene block carries no geometry of its own -- block 24, the
game's opening, has no map 24 in GEO1 and does `LOAD_AREA_MAP 64` itself --
so `LOADFILES <area>` would ask the engine for a map that does not exist.
Give the map area explicitly in that case; it defaults to the script's area,
which is right for an ordinary room.

Usage:
    bootstub.py <in.gen> <out.gen> <area> <wallset> <x> <y> [map] [facing] [--marker]
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

# Areas the engine will boot into for a new game, from the dispatch above.
ENTRIES = (0x00, 0x10)


def _imm(v):
    if v <= 0xFF:
        return bytes([0x00, v])
    return bytes([0x02]) + struct.pack("<H", v)


def _mem(v):
    return bytes([0x01]) + struct.pack("<H", v & 0xFFFF)


MARKER = b"*** MATRIX CUBED BOOT STUB ***"


def build(area, wallset, x, y, map_area=None, facing=0, marker=False):
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

    if marker:
        # A one-look answer to "is this ROM actually booting through area
        # 0x00?". Printed before anything else the stub does.
        out += bytes([op["PRINTCLEAR"]]) + bytes([0x80]) + struct.pack("<H", 1)
        out += bytes([op["CONTINUE"]])
    out += bytes([op["NEWECL"]]) + _imm(area)
    out += bytes([op["LOADFILES"]]) + _imm(area if map_area is None else map_area) \
        + _imm(0x7F) + _imm(0xFF)
    out += bytes([op["LOADPIECES"]]) + _imm(wallset)
    out += bytes([op["SAVE"]]) + _imm(y) + _mem(DUNGEON_Y)
    out += bytes([op["SAVE"]]) + _imm(x) + _mem(DUNGEON_X)
    out += bytes([op["SAVE"]]) + _imm(facing) + _mem(DUNGEON_DIR)
    out += bytes([op["NEWREGION"]]) + b"".join(
        _imm(v) for v in (0, 1, 0, 0, 0x0F, 0x0F))
    out += bytes([op["EXIT"]])
    return bytes(out)


def main():
    if len(sys.argv) < 7:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    area, wallset, x, y = (int(v, 0) for v in sys.argv[3:7])
    rest = [a for a in sys.argv[7:] if not a.startswith("--")]
    map_area = int(rest[0], 0) if rest else None
    facing = int(rest[1], 0) if len(rest) > 1 else 0

    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    ids = [b[0] for b in blocks]
    if area not in ids:
        sys.exit(f"area 0x{area:02X} not present")

    marker = "--marker" in sys.argv
    code = build(area, wallset, x, y, map_area, facing, marker)
    print(f"boot stub: {len(code)} bytes, entering area 0x{area:02X} "
          f"at ({x},{y}) with wall set {wallset}, "
          f"map area 0x{(area if map_area is None else map_area):02X}, "
          f"facing {facing}")

    # Verify the stub reads back as the instructions it was meant to be.
    table = G.load_opcodes()
    found = G.disassemble(code, table)

    claimed = sum(i.size for i in found.values())
    if claimed != len(code):
        sys.exit(f"stub does not disassemble cleanly: {claimed} of {len(code)} bytes")
    for off in sorted(found):
        print(f"    {off:04X}: {found[off].render()}")

    text = b"\0" + MARKER + b"\0" if marker else b"\0"
    for entry in ENTRIES:
        if entry not in ids or entry == area:
            continue
        slot = ids.index(entry)
        print(f"  area 0x{entry:02X}: {len(blocks[slot][1])} -> {len(code)} bytes")
        blocks[slot] = (entry, code, text)
    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(expand.read_geo_stream(rom))
    out = builder.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

"""
Transplant a complete Matrix Cubed area into the Genesis Countdown ROM.

An area is three things, and all three now convert:

    map      four-plane 16x16 grid, identical apart from a 2-byte header
    script   ECL bytecode, opcode-remapped by tools/transpile.py
    text     lifted out of the script into a separate pool, as the
             Genesis engine expects

The result is written into expanded ROM space above 1 MB, where the
cartridge's anti-tamper sum does not reach, and the loaders are retargeted.

Known limitation: variable addresses are passed through unchanged. The two
engines have different memory maps -- DOS party flags sit around
0x4C00-0x7F00, the Genesis around 0x97xx-0x9Bxx -- so a transplanted script
executes with the right structure but reads the wrong addresses. Mapping
those is the next piece of work and is tracked in docs/compatibility.md.

Areas may be added as well as replaced. Both loaders scan their id list
dynamically -- the ECL one at 0x040CE walks to a 0xFF terminator, the GEO
one at 0x5766 walks `count` entries -- so a longer list is simply found.
The ceiling is the GEO routine's 32-byte stack buffer for ids (`link a6,
#$ffde`), i.e. 32 map areas. Matrix Cubed has 33 ECL blocks, not all of
which carry maps.

Usage:
    inject_area.py <in.gen> <out.gen> <area>:<block>[:<map>] ...

A block of `-` installs a map with no script, for areas that exist only as
geometry -- `LOADFILES` names a map id, and a few of those have no ECL
block of their own.
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

import dax
import expand
import flagmap
import genesis_ecl
import integrity
import transpile


GEO_ID_CAPACITY = 32   # the stack buffer at -0x22(a6) in the GEO loader


def transplant(rom, blocks, geo, area, block_id, map_id, mc, maps, flags):
    """Put one Matrix Cubed area into the decoded directory + geo stream."""
    ids = [b[0] for b in blocks]
    if block_id is None:
        print(f"area 0x{area:02X} <- Matrix Cubed map {map_id} only (no script)")
        return install_map(geo, area, map_id, maps)

    added = area not in ids
    if added:
        blocks.append((area, b"", b""))
        ids.append(area)

    print(f"area 0x{area:02X} <- Matrix Cubed ECL block {block_id}"
          f"{f', map {map_id}' if map_id is not None else ''}"
          f"{'  (new)' if added else '  (replacing)'}")

    code, text, report = transpile.transpile(mc[block_id], flags)
    stubs = sum(1 for _, _, why in report if "counterpart" in why)
    unmapped = sum(1 for _, _, why in report if why.startswith("no Genesis mapping"))
    jumps = sum(1 for _, _, why in report if "not in layout" in why)
    old = blocks[ids.index(area)]
    print(f"  code {len(old[1])}->{len(code)}, text {len(old[2])}->{len(text)}; "
          f"{stubs} opcodes stubbed, {unmapped} variables unmapped, "
          f"{jumps} jump targets outside the decoded region")
    blocks[ids.index(area)] = (area, code, text)

    if map_id is None:
        return geo
    return install_map(geo, area, map_id, maps)


PLANES, SIDE = 4, 16

# Wall graphics Countdown treats as solid, measured over its own maps by
# cross-referencing each value against plane 3's passability bits:
#
#     value 1  1.0% passable    value 11  1.2%
#     value 5  2.1%             value 13  0.0%
#
# and the one it uses for a door:
#
#     value 6  92.9% passable
#
# A wall nibble picks a graphic from the loaded wall set, and the two games
# do not agree about what each value looks like. Matrix Cubed's door at the
# opening is 13, which Countdown draws as a solid wall -- a play session
# walked up to the closet entrance and reported "there's no door here".
#
# Only doors drawn with a graphic Countdown considers solid are repointed.
# Values it also treats as passable -- 7 is 70% in both games -- are left
# alone, since those most likely already read as an opening and guessing at
# them would trade one wrong picture for another.
SOLID_IN_COUNTDOWN = (1, 5, 11, 13)
COUNTDOWN_DOOR = 6
NIBBLES = (("N", 0, True), ("E", 0, False), ("S", 1, True), ("W", 1, False))


def door_graphics(body):
    """Draw doors as doors: a passable square side that looks like a wall."""
    out = bytearray(body)
    fixed = 0
    for sq in range(SIDE * SIDE):
        flags = out[768 + sq]
        for i, (_d, plane, high) in enumerate(NIBBLES):
            if not (flags >> (2 * i)) & 3:
                continue                   # not passable, so not a door
            b = out[plane * 256 + sq]
            v = (b >> 4) if high else (b & 15)
            if v not in SOLID_IN_COUNTDOWN:
                continue
            out[plane * 256 + sq] = ((COUNTDOWN_DOOR << 4) | (b & 15)) if high \
                else ((b & 0xF0) | COUNTDOWN_DOOR)
            fixed += 1
    return bytes(out), fixed


def flip_map(body):
    """
    Turn a DOS map north-side-up for the Genesis. NOT APPLIED -- see below.

    The two engines run their y axis opposite ways. DOS counts southward --
    its status line reads "12,4" with the marker near the top of the AREA
    map and y growing as you walk down -- while the Genesis delta table at
    0x146E0 adds +1 to DUNGEON_Y for north. Feeding DOS data straight in
    mirrors every map: rooms that belong in the north come out in the south
    and doors land on the wrong side, which is what a play session found.

    So the rows are reversed, and the north and south walls swap with them:
    a wall on the north face of (x, y) is on the south face of (x, 15-y).
    Walls live two to a byte -- plane 0 holds north in the high nibble and
    east in the low, plane 1 south and west -- and the east/west pair is
    untouched by a vertical flip.

    Planes 2 and 3 are per-square attributes and move with their square.

    This was applied and reverted. The evidence for it is real -- DOS counts
    y southward, and the delta table at 0x146E0 gives dy = 0, +1, 0, -1 for
    directions 0..3 -- but it rests on one further step that is not proven:
    that the Genesis indexes its map rows from the south. If instead row 0 is
    north in both engines, then direction 1 is SOUTH rather than north and
    the order is W, S, E, N, with no flip needed.

    Applied, it put the player somewhere that is not the DOS opening at all.
    Backed out until the engine's own map indexing is read rather than
    inferred from which way a player thought they were pointing.
    """
    out = bytearray(len(body))
    for p in range(PLANES):
        for y in range(SIDE):
            src = (SIDE - 1 - y) * SIDE
            dst = y * SIDE
            out[p * 256 + dst:p * 256 + dst + SIDE] = \
                body[p * 256 + src:p * 256 + src + SIDE]
    for sq in range(SIDE * SIDE):
        n, e = out[sq] >> 4, out[sq] & 15
        s, w = out[256 + sq] >> 4, out[256 + sq] & 15
        out[sq] = (s << 4) | e
        out[256 + sq] = (n << 4) | w
    return bytes(out)


def install_map(geo, area, map_id, maps):
    if map_id is None or map_id not in maps:
        sys.exit(f"no Matrix Cubed map {map_id}")

    count = struct.unpack_from(">H", geo, 0)[0]
    geo_ids = list(geo[2:2 + count])
    body = bytearray(geo[2 + count:])
    if area not in geo_ids:
        if count + 1 > GEO_ID_CAPACITY:
            sys.exit(f"geo id list would exceed the engine's {GEO_ID_CAPACITY}-entry buffer")
        geo_ids.append(area)
        body += bytearray(1024)
        count += 1
    gslot = geo_ids.index(area)
    # NOT FLIPPED -- see the note on flip_map.
    fixed_map, fixed = door_graphics(maps[map_id][2:])
    if fixed:
        print(f"  map {map_id}: {fixed} doors redrawn as doors")
    body[gslot * 1024:(gslot + 1) * 1024] = fixed_map
    return struct.pack(">H", count) + bytes(geo_ids) + bytes(body)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])

    specs = []
    for arg in sys.argv[3:]:
        parts = arg.split(":")
        if not 2 <= len(parts) <= 3:
            sys.exit(f"bad transplant spec {arg!r}; want <area>:<block>[:<map>]")
        specs.append((int(parts[0], 0),
                      None if parts[1] == "-" else int(parts[1], 0),
                      int(parts[2], 0) if len(parts) > 2 and parts[2] else None))

    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    geo = expand.read_geo_stream(rom)
    shipped = len(blocks)

    mc = dax.load(REPO / "dos_game/matrix/ECL1.DAX")
    maps = dax.load(REPO / "dos_game/matrix/GEO1.DAX")
    flags = flagmap.build(rom)

    for area, block_id, map_id in specs:
        if block_id is not None and block_id not in mc:
            sys.exit(f"no Matrix Cubed ECL block {block_id}; have {sorted(mc)}")
        geo = transplant(rom, blocks, geo, area, block_id, map_id, mc, maps, flags)

    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(geo)
    out = builder.finish()
    dst.write_bytes(out)
    print(f"{shipped} areas shipped, {len(blocks)} now present")
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

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
    body[gslot * 1024:(gslot + 1) * 1024] = maps[map_id][2:]
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

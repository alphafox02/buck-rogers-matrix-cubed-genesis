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

Usage:
    inject_area.py <in.gen> <out.gen> <genesis_area> <matrix_block> [matrix_map]
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

import dax
import expand
import flagmap
import genesis_ecl
import integrity
import transpile


def main():
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    area = int(sys.argv[3], 0)
    block_id = int(sys.argv[4], 0)
    map_id = int(sys.argv[5], 0) if len(sys.argv) > 5 else None

    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    ids = [b[0] for b in blocks]
    if area not in ids:
        sys.exit(f"area 0x{area:02X} not present; have {[hex(i) for i in ids]}")

    mc = dax.load(REPO / "dos_game/matrix/ECL1.DAX")
    if block_id not in mc:
        sys.exit(f"no Matrix Cubed ECL block {block_id}; have {sorted(mc)}")

    print(f"transpiling Matrix Cubed ECL block {block_id}")
    flags = flagmap.build(rom)
    code, text, report = transpile.transpile(mc[block_id], flags)
    stubs = sum(1 for _, _, why in report if "counterpart" in why)
    unmapped = sum(1 for _, _, why in report if why.startswith("no Genesis mapping"))
    jumps = sum(1 for _, _, why in report if "not in layout" in why)
    print(f"  {len(code)} bytes of bytecode, {len(text)} bytes of text")
    print(f"  {stubs} opcodes stubbed, {unmapped} variables unmapped, "
          f"{jumps} jump targets outside the decoded region")

    slot = ids.index(area)
    old = blocks[slot]
    print(f"  replacing area 0x{area:02X}: "
          f"code {len(old[1])}->{len(code)}, text {len(old[2])}->{len(text)}")
    blocks[slot] = (area, code, text)

    geo = expand.read_geo_stream(rom)
    if map_id is not None:
        maps = dax.load(REPO / "dos_game/matrix/GEO1.DAX")
        if map_id not in maps:
            sys.exit(f"no Matrix Cubed map {map_id}")
        import struct
        count = struct.unpack_from(">H", geo, 0)[0]
        geo_ids = list(geo[2:2 + count])
        body = bytearray(geo[2 + count:])
        gslot = geo_ids.index(area)
        body[gslot * 1024:(gslot + 1) * 1024] = maps[map_id][2:]
        geo = geo[:2 + count] + bytes(body)
        print(f"  map {map_id} -> area 0x{area:02X}")

    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(geo)
    out = builder.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

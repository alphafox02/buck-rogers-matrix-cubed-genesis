# SPDX-License-Identifier: MIT
"""
Transplant a Matrix Cubed dungeon map into the Genesis Countdown ROM.

The first real content conversion: DOS map data running inside SSI's own
Genesis engine.

Maps need almost no conversion -- both engines use the same four-plane 16x16
layout, and the DOS form differs only by a leading 2-byte id (see
docs/formats.md). So the transplant is: decompress the Genesis GEO stream,
substitute one area's 1024 bytes, recompress, and write it back.

Our recompressed stream is slightly larger than SSI's, so it will not fit
its original footprint. Rather than shrink it, the stream is relocated into
the run of zero padding at 0x1BBA8 and the loader's pointer is retargeted:

    0576E  lea.l  $8FA8D,a0     ->  lea.l  <new address>,a0

which is the general technique a full port needs anyway, since Matrix Cubed
needs substantially more room than Countdown's resources occupy.

Usage:
    swap_map.py <in.gen> <out.gen> <genesis_area_id> <matrix_map_id>
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

import dax
import genesis_ecl
import genesis_geo
import integrity
import lzw_encode

GEO_POINTER = 0x05770          # operand of the lea at 0x0576E
MAP_BYTES = 1024


def load_stream(rom: bytes):
    raw = genesis_ecl.decompress(rom[genesis_geo.GEO_STREAM:], limit=0x20000)
    count = struct.unpack_from(">H", raw, 0)[0]
    ids = list(raw[2:2 + count])
    body = bytearray(raw[2 + count:])
    return count, ids, body


def build(rom: bytes, area_id: int, matrix_map: bytes) -> bytes:
    count, ids, body = load_stream(rom)
    if area_id not in ids:
        raise SystemExit(f"area 0x{area_id:02X} not in {[hex(i) for i in ids]}")
    if len(matrix_map) != MAP_BYTES + 2:
        raise SystemExit(f"expected a 1026-byte DOS map, got {len(matrix_map)}")

    slot = ids.index(area_id)
    body[slot * MAP_BYTES:(slot + 1) * MAP_BYTES] = matrix_map[2:]   # drop the id header

    raw = struct.pack(">H", count) + bytes(ids) + bytes(body)
    packed = lzw_encode.compress(raw)
    room = integrity.FREE_END - integrity.FREE_START
    if len(packed) > room:
        raise SystemExit(f"stream is {len(packed)} bytes, free space is {room}")

    out = bytearray(rom)
    out[integrity.FREE_START:integrity.FREE_START + len(packed)] = packed
    struct.pack_into(">I", out, GEO_POINTER, integrity.FREE_START)
    print(f"  GEO stream {len(packed)} bytes -> 0x{integrity.FREE_START:05X}")
    print(f"  loader pointer 0x{genesis_geo.GEO_STREAM:05X} -> "
          f"0x{integrity.FREE_START:05X}")
    return integrity.repair(bytes(out))


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    area, map_id = int(sys.argv[3], 0), int(sys.argv[4], 0)
    rom = src.read_bytes()
    maps = dax.load(REPO / "dos_game/matrix/GEO1.DAX")
    if map_id not in maps:
        sys.exit(f"no Matrix Cubed map {map_id}; have {sorted(maps)}")
    print(f"transplanting Matrix Cubed map {map_id} into Genesis area 0x{area:02X}")
    out = build(rom, area, maps[map_id])
    dst.write_bytes(out)
    print(f"  checksum {'verifies' if integrity.verify(out) else 'FAILS'}")
    print(f"wrote {dst}")

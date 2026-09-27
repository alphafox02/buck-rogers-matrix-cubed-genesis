# SPDX-License-Identifier: MIT
"""
Genesis dungeon map (GEO) extraction.

The maps live at ROM 0x8FA8D as a single continuous LZW stream, loaded by
the routine at 0x05766:

    0576E  lea.l   $8FA8D,a0      ; the GEO resource
    05774  bsr.w   $9E76          ; initialise the decompressor
    0577E  bsr.w   $9ED8 (2)      ; read the map count
    0578A  bsr.w   $9ED8 (count)  ; read the id list
    ...    bsr.w   $9ED8 (0x400)  ; then one 1024-byte map at a time

So the stream is: u16 count, `count` id bytes, then `count` maps of 1024
bytes each. The Genesis uses the same four-plane 16x16 layout as the DOS
games but drops the 2-byte id header, since ids are listed up front.

Confirmed: the stream decompresses to 18452 bytes -- 2 + 18 + 18*1024
exactly -- and the ids match the ECL area numbering.
"""

import struct
from pathlib import Path

GEO_STREAM = 0x8FA8D
MAP_BYTES = 1024

import genesis_ecl
import geo


def load(rom: bytes):
    """Return [(area_id, geo.Map)] for every Genesis dungeon map."""
    raw = genesis_ecl.decompress(rom[GEO_STREAM:], limit=0x20000)
    count = struct.unpack_from(">H", raw, 0)[0]
    ids = list(raw[2:2 + count])
    body = raw[2 + count:]
    expected = count * MAP_BYTES
    if len(body) < expected:
        raise ValueError(f"expected {expected} bytes of maps, got {len(body)}")
    maps = []
    for k, area in enumerate(ids):
        chunk = body[k * MAP_BYTES:(k + 1) * MAP_BYTES]
        # geo.Map expects the DOS 2-byte header; the Genesis omits it.
        maps.append((area, geo.Map(b"\0\0" + chunk)))
    return maps


if __name__ == "__main__":
    import sys
    rom = Path(sys.argv[1] if len(sys.argv) > 1 else "roms/countdown.gen").read_bytes()
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "extracted/maps/genesis_maps.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    maps = load(rom)
    text = []
    for area, m in maps:
        w, d, i = m.stats()
        print(f"  area 0x{area:02X}  {w:3d} walled, {d:3d} doors, {i:3d} info")
        text.append(f"{'='*70}\narea 0x{area:02X} — {w} walled, {d} doors, {i} info\n"
                    f"{'='*70}\n{m.render()}\n")
    out.write_text("\n".join(text))
    print(f"\n{len(maps)} maps -> {out}")

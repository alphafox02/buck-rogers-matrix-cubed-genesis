"""
Find the palette the engine gives combat figures, by asking it.

Figure blobs carry flags 0x0000 -- no embedded palette, unlike portraits
which set 0x0008 and carry sixteen CRAM words -- so the engine supplies one
and any converted artwork has to be quantised to it. Reading it out of the
ROM did not work: 0xF16AA is a pointer table, not palettes, and matching a
known figure's tile indices against a rendered frame fails because the
engine composes the figure from hardware sprites rather than drawing the
sheet's nametable as laid out.

So this replaces a figure with a test pattern instead: sixteen horizontal
bands, one per palette index. Fight the creature under tools/play.py and the
screen shows what each index actually draws as.

Usage:
    palette_probe.py <in.gen> <out.gen> [figure_id]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import expand_figures
import genesis_ecl
import integrity
import lzw_encode

PROBE_AT = 0x1B6000        # clear of every other relocation


def build_sheet(w_tiles=18, h_tiles=9):
    """
    A sheet where every 8x8 tile is one flat palette index.

    Indices run across and down, so whatever three-by-three block of tiles
    the engine happens to draw as a figure shows nine different indices at
    once. A first attempt banded the index by pixel ROW, which only ever
    revealed two colours because a figure is three tiles tall and the bands
    repeated inside each tile.
    """
    tiles, order, nametable = {}, [], []
    for ty in range(h_tiles):
        for tx in range(w_tiles):
            idx = (ty * w_tiles + tx) % 16
            key = bytes([(idx << 4) | idx]) * 32
            if key not in tiles:
                tiles[key] = len(order)
                order.append(key)
            nametable.append(tiles[key])
    nt = b"".join(struct.pack(">H", t) for t in nametable)
    blob = struct.pack(">HHH", len(order), len(nt), 0) + nt + b"".join(order)
    return blob


def apply(rom: bytes, figure_id=0x0F) -> bytes:
    rom = bytearray(rom)
    base = struct.unpack_from(">I", rom, expand_figures.OPERANDS[0])[0]
    recs, _term = expand_figures.read(rom, base)
    blob = build_sheet()
    packed = lzw_encode.compress(blob)
    if bytes(genesis_ecl.decompress(packed, limit=0x20000)) != blob:
        raise SystemExit("probe sheet does not round trip")
    rom[PROBE_AT:PROBE_AT + len(packed)] = packed
    for k, r in enumerate(recs):
        if r[4] != figure_id:
            continue
        struct.pack_into(">I", rom, base + k * 8, PROBE_AT)
        print(f"  figure 0x{figure_id:02X} -> a sixteen-band test pattern at "
              f"0x{PROBE_AT:06X} ({len(packed)} bytes)")
        break
    else:
        raise SystemExit(f"no figure 0x{figure_id:02X} in the directory")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    fid = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x0F
    out = apply(src.read_bytes(), fid)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

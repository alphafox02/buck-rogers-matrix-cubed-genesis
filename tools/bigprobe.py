# SPDX-License-Identifier: MIT
"""
Prove the 48x48 class draws, by giving a creature a test sheet and fighting it.

tools/bigfigures.py adds size class 4 -- 36 cells through a column-major
6x6 layout table. Nothing about that is visible until the engine draws one,
so this rewrites one figure into class 4 with a sheet whose every 8x8 tile
is a flat palette index, numbered in cell order. If the class works the
screen shows a 48x48 block six tiles wide and six tall, its colours running
left to right and top to bottom. If the layout table were wrong the same
colours would appear scrambled, and if the class were ignored only a 24x24
corner would draw.

Default figure is 0x0F, RAM ASSASSIN, because it is what the first encounter
on the opening dock sends.

Usage:
    bigprobe.py <in.gen> <out.gen> [figure_id]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import expand_figures
import integrity
import lzw_encode

PROBE_AT = 0x1B7000        # clear of the figure directory and the monster stream
WIDTH = 36                 # tiles across the sheet -- 36 cells per frame
ROWS = 36                  # enough rows that any frame index the script uses lands inside
CLASS = 4


def build_sheet():
    """Every tile a flat index, numbered in cell order."""
    tiles, order, nametable = {}, [], []
    for cell in range(WIDTH * ROWS):
        idx = cell % 16
        key = bytes([(idx << 4) | idx]) * 32
        if key not in tiles:
            tiles[key] = len(order)
            order.append(key)
        nametable.append(tiles[key])
    nt = b"".join(struct.pack(">H", t) for t in nametable)
    return struct.pack(">HHH", len(order), len(nt), 0) + nt + b"".join(order)


def apply(rom: bytes, figure_id=0x0F, klass=CLASS) -> bytes:
    rom = bytearray(rom)
    blob = build_sheet()
    packed = lzw_encode.compress(blob)
    rom[PROBE_AT:PROBE_AT + len(packed)] = packed

    # expand_figures relocates the directory; read wherever the lea now points.
    at = struct.unpack_from(">I", rom, expand_figures.OPERANDS[0])[0]
    recs, _ = expand_figures.read(bytes(rom), at)
    hit = None
    for n, rec in enumerate(recs):
        if rec[4] == figure_id:
            hit = n
            break
    if hit is None:
        raise SystemExit(f"no figure 0x{figure_id:02X}")
    rec = bytearray(recs[hit])
    struct.pack_into(">I", rec, 0, PROBE_AT)
    rec[5] = WIDTH
    rec[7] = (klass << 4) | (rec[7] & 0x0F)
    rom[at + hit * 8:at + hit * 8 + 8] = rec
    print(f"  figure 0x{figure_id:02X} -> class {klass}, {WIDTH} tiles wide, "
          f"sheet at 0x{PROBE_AT:06X} ({len(packed)} bytes packed), "
          f"record at 0x{at + hit * 8:06X}")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    fid = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x0F
    kl = int(sys.argv[4], 0) if len(sys.argv) > 4 else CLASS
    out = apply(Path(sys.argv[1]).read_bytes(), fid, kl)
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

"""
Put the port's intro in the order DOS uses.

DOS composites `TITLE.DAX` blocks 2 and 3 onto ONE screen -- the Buck Rogers
logo with the copyright lines beneath it -- then shows the credits, then the
title card. The port draws the logo and the copyright block as two separate
full screens, so the copyrights appear stranded on black, and it has no credits
screen at all. A play session described the middle screen as "only got the text
that should have been on the previous screen bottom", which is exactly right.

This does two things:

* **Merges the copyright lines into the logo screen.** Rows 23-27 of
  `0x1FA000` are a single uniform tile, so the text goes there, drawn in
  palette index 8 -- the blue the separate screen used.
* **Gives the freed second slot to the credits**, which is where DOS puts
  them. That slot is drawn 40x25, so the credits screen is built to 25 rows
  rather than the 28 a full screen gets.

Both screens are rebuilt and dropped in free space, and the two `lea` operands
in the intro at 0x012FC are repointed. `trim_intro.py`'s `bra.w $15f0` at
0x001408 is left in place: with the credits in the second slot there is nothing
to add after the title card.

The container layout, which `docs/re_notes.md` had recorded wrongly:

    u16 tile count, u16 nametable bytes, u16 palette mask
    nametable
    palettes -- 32 bytes per bit set in the mask, in CRAM line order
    tiles

and the loader at 0x09D66 uploads only entries **3 to 14** of each
(`subq.l #$3,d1 / addq.l #$6,a0`), so text drawn in index 1, 2 or 15 never
reaches CRAM and the screen comes up black.

Usage:
    introfix.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dosocr
import genesis_ecl
import integrity
import lzw_encode

TITLE = 0x1FA000            # the Buck Rogers logo screen
TITLE_LEA = 0x00133A        # operand of `lea.l $1fa000.l, a0`
SECOND_LEA = 0x0013AA       # operand of `lea.l $1fb708.l, a0`
FREE, FREE_LIMIT = 0x1D3500, 0x1E0000
COLS = 40

COPYRIGHT = [
    "(C) 1992 TSR, INC.",
    "(C) 1992 THE DILLE FAMILY TRUST",
    "(C) 1992 STRATEGIC SIMULATIONS, INC.",
    "ALL RIGHTS RESERVED",
]
COPY_TOP = 23               # rows 23-26, all uniform on the shipped screen
COPY_INK = 8                # the blue the separate copyright screen used


def read(rom, addr):
    raw = genesis_ecl.decompress(rom[addr:], limit=0x20000)
    cnt, ntlen, mask = struct.unpack_from(">HHH", raw, 0)
    npal = bin(mask).count("1")
    nt = bytearray(raw[6:6 + ntlen])
    pal = raw[6 + ntlen:6 + ntlen + 32 * npal]
    tiles = [bytes(raw[6 + ntlen + 32 * npal + i * 32:][:32]) for i in range(cnt)]
    return nt, pal, tiles, mask


def build(nt, pal, tiles, mask):
    out = bytearray(struct.pack(">HHH", len(tiles), len(nt), mask))
    out += nt
    out += pal
    for t in tiles:
        out += t
    return bytes(out)


def glyph_tiles(lines, ink, bg, tiles):
    """Append tiles for `lines`, returning {(row, col): tile index}."""
    g = dosocr.glyphs()
    cache, placed = {}, {}
    for r, text in enumerate(lines):
        col0 = (COLS - len(text)) // 2
        for c, ch in enumerate(text.upper()):
            key = ch
            if key not in cache:
                bits = g.get(ch)
                t = bytearray([(bg << 4) | bg] * 32)
                if bits is not None:
                    for y in range(8):
                        for x in range(0, 8, 2):
                            hi = ink if bits[y][x] else bg
                            lo = ink if bits[y][x + 1] else bg
                            t[y * 4 + x // 2] = (hi << 4) | lo
                cache[key] = len(tiles)
                tiles.append(bytes(t))
            placed[(r, col0 + c)] = cache[key]
    return placed


def merge_title(rom):
    nt, pal, tiles, mask = read(rom, TITLE)
    first = struct.unpack_from(">H", nt, 0)[0]          # the uniform background
    bg_tile = first & 0x7FF
    bg = tiles[bg_tile][0] >> 4                         # its pixel index
    placed = glyph_tiles(COPYRIGHT, COPY_INK, bg, tiles)
    for (r, c), ti in placed.items():
        cell = (COPY_TOP + r) * COLS + c
        struct.pack_into(">H", nt, cell * 2, (first & 0xF800) | ti)
    print(f"  logo screen: {len(tiles)} tiles (was {len(tiles) - len(set(placed.values()))}),"
          f" copyright on rows {COPY_TOP}-{COPY_TOP + len(COPYRIGHT) - 1}")
    return build(nt, pal, tiles, mask)


def credits_screen(rows=25):
    import introcredits as ic
    ic.ROWS, ic.TOP = rows, 1
    tiles, nt = ic.tiles_and_map()
    return ic.container(tiles, nt)


def patch(rom: bytes):
    out = bytearray(rom)
    cursor = FREE
    for blob, lea, label in ((merge_title(rom), TITLE_LEA, "logo+copyright"),
                             (credits_screen(), SECOND_LEA, "credits")):
        packed = lzw_encode.compress(blob)
        if cursor + len(packed) > FREE_LIMIT:
            raise SystemExit("out of free space for the intro screens")
        out[cursor:cursor + len(packed)] = packed
        struct.pack_into(">I", out, lea, cursor)
        print(f"  {label:16s} {len(blob):6d} -> {len(packed):5d} packed at 0x{cursor:06X},"
              f" lea 0x{lea:06X}")
        cursor += len(packed) + 16
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = integrity.repair(patch(src.read_bytes()))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

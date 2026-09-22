"""
Put Matrix Cubed's courtesy console onto a Genesis wall as a fitting.

The port's 3D view builds its walls from five parallel ten-entry tables that
start at 0x0F170E, all indexed by the same wall set number. Table A holds the
fittings that hang on the wall -- panels, pipes, ore faces, the green-bordered
doors marked "1". Blanking that table on the Salvation dock makes exactly those
fittings disappear, which is how it was identified; see docs/re_notes.md.

Table A holds **eight pieces of 33 cells**, each piece nine cells wide, and the
renderer reaches one with `piece * 0x42` -- see `0x0B504`. The stride of nine
was measured rather than guessed: give every cell its own tile, boot, and read
plane A back out of the savestate; moving one row down the screen steps the
cell index by exactly nine.

Which piece a wall draws is data. `0x0B4EC` takes the map byte at
`0xB5A4 + row*16 + col`, keeps a nibble of it as the wall code, and looks the
code up in a sixteen-byte table chosen by the area's wall set (the ten sets
live behind the word offsets at `0x51836`). The dock issues LOADPIECES 4, so
set 1, where **wall code 8 -- the courtesy console -- is piece 5**. Painting
the console into piece 5 therefore puts it exactly where Matrix Cubed's own
map says a console stands, rather than wherever some other fitting happens to
be.

Rather than repaint tiles that other pieces share, this appends fresh tiles to
the resource and points the chosen cells at them. The loader allocates VRAM
bases in sequence, so growing a resource just shifts the ones after it and
nothing else has to know.

The DOS art is far bigger than the slot -- the console cut out of WALLDEF1 is
56x56 -- so only the informative face is kept: the screen, the colour bar and
the row of lights. At 24x32 the lettering cannot survive, but that is the same
bargain the port's own numbered doors make.

Usage:
    injectconsole.py <in.gen> <out.gen> [piece col row w h] [drawn|dos]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import genwall
import integrity
import lzw_encode

REPO = Path(__file__).resolve().parent.parent
TABLE_A = 0x0F170E          # ten entries, one per wall set
WALL_SET = 1                # what the Salvation dock uses
PIECE_W, PIECE_CELLS = 9, 33
PIECE = 5                   # wall code 8 in set 1: the courtesy console
REGION = (2, 0, 5, 4)       # where in the piece the console hangs
FREE, FREE_LIMIT = 0x1B5000, 0x1C0000
CONSOLE = REPO / "art_preview/walls/console_cut_from_atlas.png"
CROP = (96, 84, 244, 268)     # the console face alone -- no silver pillars


# Wall palette line 2, measured off the screen.
#
# Do NOT try to read this out of a GENPLUS savestate: it does not keep CRAM as
# raw Genesis colour words, so decoding 0000BBB0GGG0RRR0 at any offset gives
# invented colours -- an earlier version of this file did exactly that and the
# console came out muddy, with amber where the hardware draws grey.
#
# The honest way is to ask the machine. Flood one piece with a single colour
# index, remap the common wall codes to that piece so it fills the view, boot,
# and read the pixels back; repeat for all sixteen indices. Index 0 is
# transparent on plane A, so it reports whatever is behind it.
PALETTE = {
    1: (0, 236, 0), 2: (0, 0, 0), 3: (232, 236, 64), 4: (168, 32, 0),
    5: (232, 236, 64), 6: (200, 68, 32), 7: (136, 136, 136),
    8: (96, 32, 32), 9: (96, 68, 64), 10: (200, 100, 64),
    11: (232, 236, 232), 12: (200, 68, 32), 13: (168, 168, 0),
    14: (200, 0, 0), 15: (136, 0, 0),
}

# The dock's wall palette is entry 1 of the table at 0x0F16AA, an LZW-packed
# 38-byte block at 0x0A4584: six bytes of header then sixteen Genesis colour
# words. Decoding it matches all fourteen colours measured off the screen, so
# it is the real thing and it is ours to edit.
#
# It carries no blue and no cyan, which is the half of Matrix Cubed's spectrum
# bar that cannot otherwise be drawn. It does carry duplicates -- 3 and 5 are
# the same yellow, 6 and 12 the same orange -- and counting every pixel of all
# five set-1 tables shows how little the spares are used:
#
#     index  1   0 pixels        index  5   4 pixels
#     index  6  11 pixels        index 12  1333 pixels
#
# So 1, 5 and 6 are free for the cost of fifteen pixels elsewhere in the set,
# and repainting 5 and 6 gives the console its full blue-through-red ramp.
PAL_ENTRY = 0x0F16AA + 1 * 4
RECOLOUR = {5: (0, 0, 216), 6: (0, 216, 216)}


def genesis_word(rgb):
    r, g, b = (min(7, c // 36) for c in rgb)
    return (b << 9) | (g << 5) | (r << 1)


def repaint_palette(out: bytearray, cursor: int):
    """Give wall palette entry 1 a blue and a cyan. Returns the new cursor."""
    import genesis_ecl
    addr = struct.unpack_from(">I", out, PAL_ENTRY)[0]
    raw = bytearray(genesis_ecl.decompress(bytes(out[addr:]), limit=256))
    for i, rgb in RECOLOUR.items():
        struct.pack_into(">H", raw, 6 + i * 2, genesis_word(rgb))
    packed = lzw_encode.compress(bytes(raw))
    out[cursor:cursor + len(packed)] = packed
    struct.pack_into(">I", out, PAL_ENTRY, cursor)
    print(f"  wall palette entry 1: 0x{addr:06X} -> 0x{cursor:06X}"
          f" ({len(packed)} bytes); "
          + ", ".join(f"index {i} = {c}" for i, c in RECOLOUR.items()))
    return cursor + len(packed) + 8


def cram(state: Path, line: int):
    """The wall palette. `state` is kept for the call signature only."""
    return PALETTE


def quantise(img, pal):
    """Nearest palette entry, never index 0 -- that one is see-through."""
    px = img.load()
    out = []
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = px[x, y][:3]
            out.append(min(pal, key=lambda k:
                           (pal[k][0] - r) ** 2 + (pal[k][1] - g) ** 2
                           + (pal[k][2] - b) ** 2))
    return out



def drawn_console(w, h):
    """The console drawn at native resolution, in the measured wall palette.

    Scaling the DOS art down to 24x24 loses it: the lettering goes, the bezel
    turns to mush, and every edge lands between pixels. This keeps the DOS
    console's actual design -- metal bezel, dark screen, a spectrum bar, the
    amber plate, a row of indicator lights -- and draws each element on the
    pixel grid instead, which is what the port's own fittings do.
    """
    W, H = w * 8, h * 8
    g = [[7] * W for _ in range(H)]

    def rect(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(H, y1 + 1)):
            for x in range(max(0, x0), min(W, x1 + 1)):
                g[y][x] = c

    rect(0, 0, W - 1, H - 1, 2)            # black outline
    rect(1, 1, W - 2, H - 2, 7)            # grey body
    rect(1, 1, W - 2, 1, 11)               # lit top edge
    rect(1, H - 2, W - 2, H - 2, 9)        # shadowed bottom edge

    # the screen, inset behind a dark surround
    sx0, sy0, sx1, sy1 = 2, 3, W - 3, H // 2 - 1
    rect(sx0, sy0, sx1, sy1, 9)
    rect(sx0 + 1, sy0 + 1, sx1 - 1, sy1 - 1, 2)

    # a label across the top of the screen, lettering suggested by gaps
    ly = sy0 + 2
    rect(sx0 + 2, ly, sx1 - 2, ly + 1, 11)
    for x in range(sx0 + 4, sx1 - 2, 3):
        rect(x, ly, x, ly + 1, 2)

    # the spectrum bar: green through yellow and orange to red
    band = [1, 1, 13, 13, 3, 3, 10, 10, 6, 6, 14, 14, 15, 15]
    by = ly + 3
    span = sx1 - 2 - (sx0 + 2) + 1
    for i in range(span):
        rect(sx0 + 2 + i, by, sx0 + 2 + i, by + 1, band[i * len(band) // span])

    # a green readout line under it
    ry = by + 3
    if ry < sy1:
        for x in range(sx0 + 2, sx1 - 1, 2):
            rect(x, ry, x, ry, 1)

    # the amber plate
    py0 = sy1 + 2
    rect(2, py0, W - 3, py0 + 2, 2)
    rect(3, py0 + 1, W - 4, py0 + 1, 3)

    # the row of indicator lights
    iy = py0 + 4
    rect(2, iy, W - 3, iy + 1, 9)
    for i, x in enumerate(range(3, W - 3, 3)):
        rect(x, iy, x + 1, iy + 1, (14, 3, 1)[i % 3])

    # a plinth along the bottom
    rect(1, H - 4, W - 2, H - 3, 9)
    return [v for row in g for v in row]


def to_tiles(idx, w, h):
    """A w*8 by h*8 index buffer, cut into 4bpp Genesis tiles."""
    tiles = []
    for ty in range(h):
        for tx in range(w):
            t = bytearray(32)
            for y in range(8):
                for x in range(0, 8, 2):
                    hi = idx[(ty * 8 + y) * (w * 8) + tx * 8 + x]
                    lo = idx[(ty * 8 + y) * (w * 8) + tx * 8 + x + 1]
                    t[y * 4 + x // 2] = (hi << 4) | lo
            tiles.append(bytes(t))
    return tiles


def build(rom: bytes, piece: int, region, state: Path, preview=None,
          style="dos", recolour=True):
    from PIL import Image
    entry = TABLE_A + WALL_SET * 4
    addr = struct.unpack_from(">I", rom, entry)[0]
    tiles, nt, _ = genwall.read(rom, addr)

    col, row, w, h = region
    cells = [piece * PIECE_CELLS + (row + y) * PIECE_W + col + x
             for y in range(h) for x in range(w)]
    line = (struct.unpack_from(">H", nt, cells[0] * 2)[0] >> 13) & 3
    pal = cram(state, line)

    pal = dict(pal)
    if recolour:
        pal.update(RECOLOUR)
    if style == "dos":
        art = Image.open(CONSOLE).convert("RGB").crop(CROP)
        art = art.resize((w * 8, h * 8), Image.LANCZOS)
        idx = quantise(art, pal)
    else:
        idx = drawn_console(w, h)
    if preview:
        out = Image.new("RGB", (w * 8, h * 8))
        for i, v in enumerate(idx):
            out.putpixel((i % (w * 8), i // (w * 8)), pal[v])
        out.resize((out.width * 8, out.height * 8), Image.NEAREST).save(preview)

    new_tiles = list(tiles) + to_tiles(idx, w, h)
    new_nt = bytearray(nt)
    for i, cell in enumerate(cells):
        struct.pack_into(">H", new_nt, cell * 2, (line << 13) | (len(tiles) + i))

    blob = genwall.build(new_tiles, bytes(new_nt))
    packed = lzw_encode.compress(blob)
    if FREE + len(packed) > FREE_LIMIT:
        raise SystemExit("out of free space")
    out = bytearray(rom)
    out[FREE:FREE + len(packed)] = packed
    struct.pack_into(">I", out, entry, FREE)
    cursor = FREE + len(packed) + 8
    if recolour:
        cursor = repaint_palette(out, cursor)
    print(f"  wall set {WALL_SET} table A: 0x{addr:06X}, {len(tiles)} tiles"
          f" -> {len(new_tiles)}; piece {piece} cells {cells[0]}-{cells[-1]}"
          f" ({w}x{h} at col {col}, row {row}) on palette {line}")
    print(f"  {len(packed)} bytes at 0x{FREE:06X}; table entry 0x{entry:06X} repointed")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    nums = [a for a in sys.argv[3:] if a.isdigit()]
    piece = int(nums[0]) if nums else PIECE
    region = tuple(int(n) for n in nums[1:5]) if len(nums) >= 5 else REGION
    style = next((a for a in sys.argv[3:] if a in ("drawn", "dos")), "dos")
    recolour = "--nopal" not in sys.argv[3:]
    state = Path(sys.argv[-1]) if sys.argv[-1].endswith(".state") else None
    out = build(src.read_bytes(), piece, region, state, style=style,
                recolour=recolour,
                preview=REPO / "art_preview/walls/06_console_piece.png")
    out = integrity.repair(out)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

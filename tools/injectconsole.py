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
    injectconsole.py <in.gen> <out.gen> [piece col row w h]
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
REGION = (3, 0, 3, 3)       # where in the piece the console hangs
FREE, FREE_LIMIT = 0x1B5000, 0x1C0000
CONSOLE = REPO / "art_preview/walls/console_cut_from_atlas.png"
CROP = (96, 84, 244, 268)     # the console face alone -- no silver pillars


def cram(state: Path, line: int):
    """One palette line as RGB, read from a savestate rather than guessed."""
    st = state.read_bytes()
    out = []
    for i in range(16):
        w = struct.unpack_from(">H", st, 0x22424 + (line * 16 + i) * 2)[0]
        out.append((((w >> 1) & 7) * 36, ((w >> 5) & 7) * 36, ((w >> 9) & 7) * 36))
    return out


def quantise(img, pal):
    """Nearest palette entry, never index 0 -- that one is see-through."""
    px = img.load()
    out = []
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = px[x, y][:3]
            out.append(min(range(1, 16), key=lambda k:
                           (pal[k][0] - r) ** 2 + (pal[k][1] - g) ** 2
                           + (pal[k][2] - b) ** 2))
    return out


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


def build(rom: bytes, piece: int, region, state: Path, preview=None):
    from PIL import Image
    entry = TABLE_A + WALL_SET * 4
    addr = struct.unpack_from(">I", rom, entry)[0]
    tiles, nt, _ = genwall.read(rom, addr)

    col, row, w, h = region
    cells = [piece * PIECE_CELLS + (row + y) * PIECE_W + col + x
             for y in range(h) for x in range(w)]
    line = (struct.unpack_from(">H", nt, cells[0] * 2)[0] >> 13) & 3
    pal = cram(state, line)

    art = Image.open(CONSOLE).convert("RGB").crop(CROP)
    art = art.resize((w * 8, h * 8), Image.LANCZOS)
    idx = quantise(art, pal)
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
    print(f"  wall set {WALL_SET} table A: 0x{addr:06X}, {len(tiles)} tiles"
          f" -> {len(new_tiles)}; piece {piece} cells {cells[0]}-{cells[-1]}"
          f" ({w}x{h} at col {col}, row {row}) on palette {line}")
    print(f"  {len(packed)} bytes at 0x{FREE:06X}; table entry 0x{entry:06X} repointed")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    piece = int(sys.argv[3]) if len(sys.argv) > 3 else PIECE
    region = tuple(int(a) for a in sys.argv[4:8]) if len(sys.argv) > 7 else REGION
    state = Path(sys.argv[8]) if len(sys.argv) > 8 else REPO / "step.state"
    out = integrity.repair(build(src.read_bytes(), piece, region, state,
                                 REPO / "art_preview/walls/08_console_piece.png"))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

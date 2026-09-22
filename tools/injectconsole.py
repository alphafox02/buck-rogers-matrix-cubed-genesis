"""
Put Matrix Cubed's courtesy console onto a Genesis wall as a fitting.

The port's 3D view builds its walls from five parallel ten-entry tables that
start at 0x0F170E, all indexed by the same wall set number. Table A holds the
fittings that hang on the wall -- panels, pipes, ore faces, the green-bordered
doors marked "1". Blanking that table on the Salvation dock makes exactly those
fittings disappear, which is how it was identified; see docs/re_notes.md.

Table A is not a list of pieces. It is one atlas, nine cells wide and thirty
rows tall, and the renderer copies a window of it to the screen. The width was
measured, not guessed: give every cell its own tile, boot, and read the plane
back -- moving one row down the screen steps the cell index by exactly nine.

A console is a fitting, so it goes in the atlas. Rather than repaint tiles that
other regions share, this appends fresh tiles to the resource and points the
chosen atlas cells at them. The loader allocates VRAM bases in sequence, so
growing a resource just shifts the ones after it and nothing else has to know.

The DOS art is far bigger than the slot -- the console cut out of WALLDEF1 is
56x56 -- so only the informative face is kept: the screen, the colour bar and
the row of lights. At 24x32 the lettering cannot survive, but that is the same
bargain the port's own numbered doors make.

Usage:
    injectconsole.py <in.gen> <out.gen> [col row w h]
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
ATLAS_W = 9
REGION = (1, 11, 4, 4)     # the left numbered door, in atlas cells
FREE, FREE_LIMIT = 0x1B5000, 0x1C0000
CONSOLE = REPO / "art_preview/walls/console_cut_from_atlas.png"
CROP = (40, 84, 300, 340)     # the console face and its pillars, 260x256


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


def build(rom: bytes, region, state: Path, preview=None):
    from PIL import Image
    entry = TABLE_A + WALL_SET * 4
    addr = struct.unpack_from(">I", rom, entry)[0]
    tiles, nt, _ = genwall.read(rom, addr)

    col, row, w, h = region
    cells = [(row + y) * ATLAS_W + col + x for y in range(h) for x in range(w)]
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
          f" -> {len(new_tiles)}; atlas cells {cells[0]}-{cells[-1]}"
          f" ({w}x{h} at col {col}, row {row}) on palette {line}")
    print(f"  {len(packed)} bytes at 0x{FREE:06X}; table entry 0x{entry:06X} repointed")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    region = tuple(int(a) for a in sys.argv[3:7]) if len(sys.argv) > 6 else REGION
    state = Path(sys.argv[7]) if len(sys.argv) > 7 else REPO / "step.state"
    out = integrity.repair(build(src.read_bytes(), region, state,
                                 REPO / "art_preview/walls/08_console_piece.png"))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

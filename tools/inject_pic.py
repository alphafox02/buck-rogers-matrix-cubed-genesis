"""
Put Matrix Cubed's own artwork into the Genesis picture directory.

The engine resolves `PICTURE <id>` through a 110-entry table of 32-bit
pointers at 0xF14F2 (see docs/re_notes.md). Each points at a blob
compressed with the same codec as the ECL and GEO streams, holding:

     0  2  unique tile count
     2  2  nametable size in bytes
     4  2  flags
     6  .. nametable, one big-endian word per cell
    ..  .. tile data, 32 bytes each, VDP 4bpp, high nibble = left pixel

Icons are 3x3 tiles, 24x24 pixels. Matrix Cubed's portraits are 88x88, so
they are reduced to the slot the Genesis port designed rather than pasted
in at source size -- the port shows icons where DOS shows portraits, and
that is a decision SSI already made.

**The container carries no palette.** Colour comes from a separate table of
16-word CRAM palettes at 0xF16AA, selected by 0x9AFB -- which `LOADPIECES`
sets to its id divided by three. So art injected for an area must be
quantised against the palette that area loads, and the same id used under a
different palette will not look the same. That is a property of the engine,
not of this tool.

Pointers are rewritten in place, so the directory does not move and no
relocation is needed. The blob goes into expanded ROM above the streams
`tools/expand.py` relocates. The directory sits inside the region the
cartridge checksums, so the sum is repaired afterwards.

Usage:
    inject_pic.py <in.gen> <out.gen> <id>:<archive>/<name>[:<palette>] ...

Each picture takes the palette of the area that uses it most, since that is
the palette it will actually be seen under.
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import genesis_ecl
import integrity
import lzw_encode

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")

PICTURE_DIR = 0xF14F2
PICTURE_COUNT = 110
PALETTE_DIR = 0xF16AA
ART_BASE = 0x1C0000          # past everything expand.py relocates
TILE = 8
ICON_TILES = 3               # 3x3 tiles, 24x24 pixels


def read_palette(rom, index):
    """The 16 CRAM words of one palette, as RGB triples."""
    ptr = struct.unpack_from(">I", rom, PALETTE_DIR + index * 4)[0]
    raw = genesis_ecl.decompress(rom[ptr:ptr + 0x400], limit=0x400)
    out = []
    for i in range(16):
        w = struct.unpack_from(">H", raw, i * 2)[0]
        r, g, b = (w >> 0) & 0xE, (w >> 4) & 0xE, (w >> 8) & 0xE
        out.append(((r >> 1) * 36, (g >> 1) * 36, (b >> 1) * 36))
    return out


def _nearest(r, g, b, palette):
    best, bd = 0, None
    for i, (pr, pg, pb) in enumerate(palette):
        # Perceptual weights applied to each channel difference before
        # squaring -- squaring the weight instead crushes blue and turns
        # browns purple.
        d = (0.30 * (r - pr)) ** 2 + (0.59 * (g - pg)) ** 2 + (0.11 * (b - pb)) ** 2
        if bd is None or d < bd:
            best, bd = i, d
    return best


def quantise(img, palette):
    """Flat nearest-colour match, deliberately without error diffusion.

    Floyd-Steinberg was tried and is worse here. At 24x24 an icon is 576
    pixels, and the dither noise reads as noise rather than as colour: mean
    error rose from 54.9 to 60.2 and the contact sheet looks visibly
    dirtier. Diffusion pays off over a 300x200 background, not over a
    three-tile icon.

    The quality ceiling is the palette, not the algorithm. The container
    carries no colours of its own -- they come from the area's palette at
    0xF16AA, which SSI tuned for Countdown's own icons -- so blues and
    greens in Matrix Cubed's portraits have nowhere to go.
    """
    px = img.convert("RGB").load()
    w, h = img.size
    return [[_nearest(*px[x, y], palette) for x in range(w)] for y in range(h)]


def build(indices):
    """Pack an indexed bitmap into (tile bytes, nametable)."""
    h, w = len(indices), len(indices[0])
    cols, rows = w // TILE, h // TILE
    tiles, order, nm = {}, [], []
    for ty in range(rows):
        for tx in range(cols):
            raw = bytearray()
            for y in range(TILE):
                for x in range(0, TILE, 2):
                    hi = indices[ty * TILE + y][tx * TILE + x]
                    lo = indices[ty * TILE + y][tx * TILE + x + 1]
                    raw.append((hi << 4) | lo)
            key = bytes(raw)
            if key not in tiles:
                tiles[key] = len(order)
                order.append(key)
            nm.append(tiles[key])
    return b"".join(order), nm


def container(tiles, nm):
    out = struct.pack(">HHH", len(tiles) // 32, len(nm) * 2, 0)
    out += b"".join(struct.pack(">H", e) for e in nm)
    return out + tiles


def main():
    args = sys.argv[1:]
    if len(args) < 3:
        sys.exit(__doc__)
    src, dst, specs = Path(args[0]), Path(args[1]), args[2:]

    rom = bytearray(src.read_bytes())
    cache = {}

    cursor = ART_BASE
    for spec in specs:
        parts = spec.split(":")
        pid, path = int(parts[0], 0), parts[1]
        pal_index = int(parts[2], 0) if len(parts) > 2 else 1
        if pal_index not in cache:
            cache[pal_index] = read_palette(bytes(rom), pal_index)
        palette = cache[pal_index]
        if not 0 <= pid < PICTURE_COUNT:
            sys.exit(f"picture id {pid} is outside the {PICTURE_COUNT}-entry directory")
        png = REPO / "extracted" / "images_vd" / f"{path}.png"
        if not png.exists():
            png = REPO / "extracted" / "images" / f"{path}.png"
        if not png.exists():
            sys.exit(f"no such image: {path}")

        img = Image.open(png).convert("RGB")
        side = ICON_TILES * TILE
        img = img.resize((side, side), Image.LANCZOS)
        tiles, nm = build(quantise(img, palette))
        blob = container(tiles, nm)
        packed = lzw_encode.compress(blob)
        if genesis_ecl.decompress(packed, limit=0x4000) != blob:
            sys.exit(f"compressed {path} does not round-trip")

        old = struct.unpack_from(">I", rom, PICTURE_DIR + pid * 4)[0]
        rom[cursor:cursor + len(packed)] = packed
        struct.pack_into(">I", rom, PICTURE_DIR + pid * 4, cursor)
        print(f"  picture 0x{pid:02X}: {path} pal {pal_index} -> "
              f"{len(tiles)//32} tiles, {len(packed)} packed at 0x{cursor:06X} "
              f"(was 0x{old:06X})")
        cursor += len(packed) + 2

    out = integrity.repair(bytes(rom))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

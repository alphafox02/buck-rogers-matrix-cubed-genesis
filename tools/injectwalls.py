"""
Put Matrix Cubed's wall pixels into the Genesis wall sets.

The creatures went in this way and the walls are the same shape of problem:
a known container, a known loader, new art. What took a while was believing
it, because the wall resources are LZW-compressed and their headers read as
nonsense until you decompress them.

A resource is a tile count, a nametable length, a zero word, the nametable
as ordinary Genesis words, and then the tiles at 32 bytes each. This keeps
the NAMETABLE exactly as it is -- so the corridors keep Countdown's
geometry, which is known to draw correctly -- and replaces only the tile
graphics with Matrix Cubed's, converted to 4bpp.

Each Genesis tile is paired with the deco tile whose pixel structure is
closest, so an edge stays an edge and a flat face stays flat; only the
texture changes. The palette is not guessed: it is read back off a
screenshot of the port, by pairing a tile's 4bpp indices with the colours
actually on screen.

Usage:
    injectwalls.py <in.gen> <out.gen> [deco]
"""

import glob
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import genesis_ecl
import genwall
import integrity
import lzw_encode

REPO = Path(__file__).resolve().parent.parent
TILES = REPO / "extracted/images/8X8D1"
FREE, FREE_LIMIT = 0x1B5000, 0x1C0000     # as inject_creature uses

# The wall set the port's areas fall to ([0xB52A] reads 3 on the dock), and
# where its loader case takes each resource.
#
# WRONG TARGET, kept as the worked example: repainting these two changed the
# status panel on the right of the screen and left the corridor alone, so
# whatever they feed, it is not the walls. The loader case does put them in
# the wall slots [0xB53E]/[0xB542] -- which on the dock hold 0xFFB458 and
# 0xFFB45E, pointers into RAM, so 0x9DD4 is handing back reader state rather
# than a decompressed blob, and the trail continues from there.
RESOURCES = {0x0918A8: 0x0849C + 2, 0x0EBE89: 0x084AA + 2}

# Read off a port screenshot: the 4bpp index each colour is drawn with.
PALETTE = {1: (232, 0, 0), 2: (0, 0, 0), 3: (64, 0, 32), 4: (136, 0, 0),
           5: (232, 68, 0), 7: (136, 136, 136), 8: (64, 68, 64),
           10: (136, 136, 136), 11: (64, 68, 64), 13: (0, 136, 0),
           15: (232, 236, 232)}


def dos_tiles(deco):
    import numpy as np
    from PIL import Image
    out = {}
    for f in glob.glob(str(TILES / ("%03d_*.png" % deco))):
        n = int(re.search(r"_(\d+)\.png", f).group(1))
        out[n] = np.asarray(Image.open(f).convert("RGB")).astype(int)
    return out


def to_4bpp(img):
    """Quantise an 8x8 RGB tile to the wall palette, as a 32-byte tile."""
    idx = []
    for y in range(8):
        for x in range(8):
            r, g, b = img[y][x]
            best = min(PALETTE, key=lambda k: (PALETTE[k][0] - r) ** 2
                       + (PALETTE[k][1] - g) ** 2 + (PALETTE[k][2] - b) ** 2)
            idx.append(best)
    out = bytearray(32)
    for i in range(0, 64, 2):
        out[i // 2] = (idx[i] << 4) | idx[i + 1]
    return bytes(out)


def structure(px):
    """Which pixels share a value -- the shape, independent of colour."""
    seen, out = {}, []
    for v in px:
        if v not in seen:
            seen[v] = len(seen)
        out.append(seen[v])
    return out


def px_of(tile):
    out = []
    for y in range(8):
        for x in range(8):
            b = tile[y * 4 + x // 2]
            out.append((b >> 4) if x % 2 == 0 else (b & 0xF))
    return out


def px_of_rgb(img):
    flat = [tuple(img[y][x]) for y in range(8) for x in range(8)]
    return flat


def pair_tiles(gen_tiles, art):
    """For each Genesis tile, the deco tile closest in structure."""
    dos = {n: structure(px_of_rgb(im)) for n, im in art.items()}
    out = []
    for t in gen_tiles:
        want = structure(px_of(t))
        best = min(dos, key=lambda n: sum(1 for a, b in zip(want, dos[n]) if a != b))
        out.append(best)
    return out


def rebuild(rom: bytes, deco=5):
    art = dos_tiles(deco)
    out = bytearray(rom)
    cursor = FREE
    for addr, lea_at in RESOURCES.items():
        tiles, nt, raw = genwall.read(rom, addr)
        chosen = pair_tiles(tiles, art)
        new = [to_4bpp(art[c]) for c in chosen]
        blob = genwall.build(new, nt)
        packed = lzw_encode.compress(blob)
        if cursor + len(packed) > FREE_LIMIT:
            raise SystemExit("out of free space for wall art")
        out[cursor:cursor + len(packed)] = packed
        struct.pack_into(">I", out, lea_at, cursor)
        print(f"  0x{addr:06X}: {len(tiles)} tiles repainted -> 0x{cursor:06X}"
              f" ({len(packed)} bytes), lea at 0x{lea_at:05X}")
        cursor += len(packed) + 16
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    deco = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    out = rebuild(src.read_bytes(), deco)
    out = integrity.repair(out)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'needs fixing'}; wrote {dst}")

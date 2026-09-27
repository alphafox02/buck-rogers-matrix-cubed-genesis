# SPDX-License-Identifier: MIT
"""
Redraw the title card with more than sixteen colours.

The card behind the main menu is Matrix Cubed over Jupiter, and at sixteen
colours it is the worst-looking thing in the port: the lettering's blue-to-white
gradient dithers into noise and the starfield turns into a checkerboard. Mean
per-channel error against the DOS original is 42.

The Genesis is not limited to sixteen here. A nametable word carries a palette
line in bits 13-14, so every 8x8 cell can pick one of four, and the container's
flag word is a bitmask of which lines it ships (0x09D66 reads 32 bytes per bit
set, in line order). Two lines is about thirty colours.

Two lines and not four, on purpose: the menu's own icons and text are drawn over
this card and use the other lines. Taking all four would repaint them.

This card is also one of only two loads that set `[0xB4BD]` first (`0x0088FE`),
so all sixteen entries of each line upload rather than the twelve a portrait
gets. Index 0 is still transparent on a plane, so fifteen per line are usable.

Budget: the stream carries no length and the engine expands it into whatever is
free, so the blob must not exceed the original's decompressed size. Tiles that
differ in a few pixels are merged until it fits, which costs less than dropping
colours.

Usage:
    titlecard.py <in.gen> <out.gen> [--lines N]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import genesis_ecl
import integrity
import inject_portrait as ip
import lzw_encode
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
OPERAND = 0x088FA               # lea operand of the menu card
W, H = 36, 16                   # 288x128
FREE, FREE_LIMIT = 0x1D6000, 0x1E0000
SOURCE = REPO / "extracted/images/TITLE/004.png"
LINES = (2, 3)                  # leave 0 and 1 to the menu's own art


def source():
    im = Image.open(SOURCE).convert("RGB")
    im = im.resize((W * 8, int(im.height * W * 8 / im.width)), Image.LANCZOS)
    out = Image.new("RGB", (W * 8, H * 8), (0, 0, 0))
    out.paste(im, (0, (H * 8 - im.height) // 2))
    return out


def tile_pixels(im, tx, ty):
    px = im.load()
    return [px[tx * 8 + x, ty * 8 + y] for y in range(8) for x in range(8)]


def palettes(im, count):
    """`count` palettes of fifteen, and which tiles use each."""
    # One generous palette first, then split its colours into `count` groups
    # by k-means, so the groups fall where the picture's colours actually are
    # rather than on an arbitrary split.
    words, rgb = ip.build_palette([im], 15 * count)
    seeds = rgb[1:]
    groups = [seeds[i::count] for i in range(count)]
    for _ in range(8):
        assign = [[] for _ in range(count)]
        for tx in range(W):
            for ty in range(H):
                pix = tile_pixels(im, tx, ty)
                best, bd = 0, None
                for g, pal in enumerate(groups):
                    d = sum(min(ip.distance(p, c) for c in pal) for p in pix)
                    if bd is None or d < bd:
                        best, bd = g, d
                assign[best].append((tx, ty))
        new = []
        for g in range(count):
            if not assign[g]:
                new.append(groups[g])
                continue
            sub = Image.new("RGB", (8, 8 * max(1, len(assign[g]))))
            for k, (tx, ty) in enumerate(assign[g]):
                sub.paste(im.crop((tx*8, ty*8, tx*8+8, ty*8+8)), (0, k*8))
            _w, r = ip.build_palette([sub], 15)
            new.append(r[1:])
        if new == groups:
            break
        groups = new
    return groups, assign


def encode(im, groups, assign, tolerance):
    owner = {}
    for g, cells in enumerate(assign):
        for c in cells:
            owner[c] = g
    tiles, order, nm = {}, [], []
    for ty in range(H):
        for tx in range(W):
            g = owner.get((tx, ty), 0)
            pal = groups[g]
            raw = bytearray()
            pix = tile_pixels(im, tx, ty)
            for y in range(8):
                for x in range(0, 8, 2):
                    hi = ip.nearest(pix[y*8 + x], pal) + 1
                    lo = ip.nearest(pix[y*8 + x + 1], pal) + 1
                    raw.append((hi << 4) | lo)
            key = (g, bytes(raw))
            if key not in tiles:
                hit = None
                if tolerance:
                    for i, (og, ob) in enumerate(order):
                        if og != g:
                            continue
                        d = sum((1 if (a >> 4) != (b >> 4) else 0)
                                + (1 if (a & 15) != (b & 15) else 0)
                                for a, b in zip(raw, ob))
                        if d <= tolerance:
                            hit = i
                            break
                if hit is None:
                    tiles[key] = len(order)
                    order.append((g, bytes(raw)))
                else:
                    tiles[key] = hit
            nm.append(tiles[key] | (LINES[g] << 13))
    blob = struct.pack(">HHH", len(order), len(nm) * 2,
                       sum(1 << l for l in LINES))
    blob += b"".join(struct.pack(">H", e) for e in nm)
    for g in range(len(groups)):
        words = [0] + [ip.cram(c)[0] for c in groups[g]]
        blob += b"".join(struct.pack(">H", w) for w in words[:16])
        blob += b"\x00" * (32 - 2 * len(words[:16]))
    blob += b"".join(b for _g, b in order)
    return blob, len(order)


def build(rom: bytes):
    im = source()
    old = struct.unpack_from(">I", rom, OPERAND)[0]
    was = genesis_ecl.decompress(rom[old:], limit=0x40000)
    groups, assign = palettes(im, len(LINES))
    for tol in range(0, 64):
        blob, ntiles = encode(im, groups, assign, tol)
        if len(blob) <= len(was):
            break
    else:
        raise SystemExit("cannot fit the card in its budget")
    packed = lzw_encode.compress(blob)
    if genesis_ecl.decompress(packed, limit=0x40000) != blob:
        raise SystemExit("card does not round-trip")
    out = bytearray(rom)
    out[FREE:FREE + len(packed)] = packed
    struct.pack_into(">I", out, OPERAND, FREE)
    print(f"  {len(LINES)} palettes, {ntiles} tiles, merge tolerance {tol}, "
          f"{len(blob)}/{len(was)} bytes -> {len(packed)} packed at 0x{FREE:06X}")
    return bytes(out), blob


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out, _ = build(src.read_bytes())
    out = integrity.repair(out)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

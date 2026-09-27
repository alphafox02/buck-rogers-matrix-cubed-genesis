# SPDX-License-Identifier: MIT
"""
Decode the Genesis engine's picture container.

Found by walking back from the `"loadpieces error 1"` site: the loader at
0x09BB6 resolves resources through directories of 8-byte records, and the
blobs they point at decompress with the same codec as the ECL and GEO
streams (`genesis_ecl.decompress`).

    0  2  unique tile count
    2  2  nametable size in BYTES (entries * 2)
    4  2  flags -- 0 in every resource found so far
    6  .. nametable, one big-endian word per cell, tile index in bits 0-10
    .. .. tile data, 32 bytes each, VDP 4bpp, high nibble = left pixel

Self-validating: total length is exactly 6 + nametable_bytes + 32 * tiles
for every one of the 247 resources located this way, which is what makes a
blind scan safe. Width comes from the directory record's `chunk` byte, in
tiles; height is whatever the entry count divides into.

Usage:
    genesis_pic.py <rom> [out_dir]     dump every picture found as PNG
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import genesis_ecl

FIGURE_DIR = 0x09A14     # 8-byte records, ids 0x00-0x40
POINTER_DIR = 0x0998C    # 4-byte pointers

# The real ECL picture directories, found by following the PICTURE opcode
# through 0x03662 -> 0x04DFA -> 0x08516 -> 0x0B766 / 0x0B7B4. Each is an
# id list terminated by a negative byte, paired with an array of 32-bit
# pointers.
PICTURE_IDS, PICTURE_PTRS = 0x51326, 0x51360     # ids 0x20-0x6F, 57 entries
BIGPIC_IDS, BIGPIC_PTRS = 0x51302, 0x5130A       # ids 0x70-0x78, VIEW

PORTRAIT_CELLS = 121     # 11x11 tiles, 88x88 pixels, usually six frames
BIGPIC_WIDTH = 36        # 36x15 tiles, 288x120 pixels


def decode(blob):
    """Return (tiles, nametable, flags, palette) or None.

    Flags bit 3 means a 16-word CRAM palette sits between the nametable and
    the tile data -- the ECL pictures and big pictures carry their own
    colours, where the small icons do not. That is what makes injecting
    artwork here worthwhile: the palette comes with the image instead of
    being whatever the area happens to have loaded.
    """
    if len(blob) < 6:
        return None
    n, map_bytes, flags = struct.unpack_from(">HHH", blob, 0)
    if n == 0 or map_bytes == 0 or map_bytes % 2 or map_bytes > 8192 or n > 4000:
        return None
    # Bit 3 and bit 2 both mean a 16-word palette follows the nametable. The
    # title screen and the world maps use bit 2; the ECL pictures use bit 3.
    pal_bytes = 32 if flags & 0x0C else 0
    if len(blob) != 6 + map_bytes + pal_bytes + 32 * n:
        return None
    entries = map_bytes // 2
    nm = [struct.unpack_from(">H", blob, 6 + 2 * i)[0] for i in range(entries)]
    at = 6 + map_bytes
    palette = None
    if pal_bytes:
        palette = []
        for i in range(16):
            w = struct.unpack_from(">H", blob, at + i * 2)[0]
            r, g, b = (w >> 0) & 0xE, (w >> 4) & 0xE, (w >> 8) & 0xE
            palette.append(((r >> 1) * 36, (g >> 1) * 36, (b >> 1) * 36))
    return blob[at + pal_bytes:], nm, flags, palette


def at(rom, ptr, limit=0x8000):
    try:
        return decode(genesis_ecl.decompress(rom[ptr:ptr + limit], limit=limit))
    except Exception:
        return None


def scan(rom):
    """Every address in the ROM that a 32-bit word points at and that decodes."""
    seen, out = set(), []
    for a in range(0x200, len(rom) - 4, 2):
        v = struct.unpack_from(">I", rom, a)[0]
        if not 0x10000 <= v < len(rom) or v in seen:
            continue
        seen.add(v)
        got = at(rom, v)
        if got:
            out.append((v, got))
    return out


def render(tiles, nm, width, palette=None):
    from PIL import Image
    height = (len(nm) + width - 1) // width
    img = Image.new("P", (width * 8, height * 8))
    flat = ([c for rgb in palette for c in rgb] if palette
            else [(i * 17) % 256 for i in range(16) for _ in range(3)])
    img.putpalette(flat + [0] * (768 - len(flat)))
    px = img.load()
    for i, e in enumerate(nm):
        ti = e & 0x7FF
        base = ti * 32
        if base + 32 > len(tiles):
            continue
        tx, ty = (i % width) * 8, (i // width) * 8
        for row in range(8):
            for col in range(8):
                b = tiles[base + row * 4 + col // 2]
                px[tx + col, ty + row] = (b >> 4) if col % 2 == 0 else (b & 0xF)
    return img


def main():
    rom = Path(sys.argv[1]).read_bytes()
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "extracted/genesis_pics")
    out.mkdir(parents=True, exist_ok=True)
    # Widths the directories declare, keyed by entry count where known.
    WIDTH = {162: 18, 324: 36, 9: 3, 270: 18, 232: 8, 264: 24, 437: 19, 144: 12,
             112: 8, 64: 8, 27: 3, 18: 3}
    found = scan(rom)
    print(f"{len(found)} picture resources")
    for ptr, got in found:
        tiles, nm, flags, palette = got
        if palette and len(nm) % PORTRAIT_CELLS == 0:
            w = 11                       # a portrait, one frame under the next
        elif palette:
            w = BIGPIC_WIDTH
        else:
            w = WIDTH.get(len(nm)) or max(1, int(len(nm) ** 0.5))
        render(tiles, nm, w, palette).save(out / f"{ptr:06X}.png")
    print(f"wrote {len(found)} PNGs to {out}")


if __name__ == "__main__":
    main()

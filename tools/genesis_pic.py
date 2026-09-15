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


def decode(blob):
    """Return (tiles, nametable, flags) or None if this is not a picture."""
    if len(blob) < 6:
        return None
    n, map_bytes, flags = struct.unpack_from(">HHH", blob, 0)
    if n == 0 or map_bytes == 0 or map_bytes % 2 or map_bytes > 4096 or n > 2000:
        return None
    if len(blob) != 6 + map_bytes + 32 * n:
        return None
    entries = map_bytes // 2
    nm = [struct.unpack_from(">H", blob, 6 + 2 * i)[0] for i in range(entries)]
    return blob[6 + map_bytes:], nm, flags


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


def render(tiles, nm, width):
    from PIL import Image
    height = (len(nm) + width - 1) // width
    img = Image.new("P", (width * 8, height * 8))
    img.putpalette([(i * 17) % 256 for i in range(16) for _ in range(3)] + [0] * (768 - 48))
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
    for ptr, (tiles, nm, flags) in found:
        w = WIDTH.get(len(nm)) or max(1, int(len(nm) ** 0.5))
        render(tiles, nm, w).save(out / f"{ptr:06X}.png")
    print(f"wrote {len(found)} PNGs to {out}")


if __name__ == "__main__":
    main()

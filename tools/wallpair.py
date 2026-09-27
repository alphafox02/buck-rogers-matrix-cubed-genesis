# SPDX-License-Identifier: MIT
"""
Pair Genesis wall tiles with Matrix Cubed's, by standing in the same place.

Both engines draw the dock from the same 16x16 map, so from the same square
facing the same way the two views show the same corridor -- Countdown's
pieces in one, Matrix Cubed's in the other. Matching each screenshot's 8x8
cells back to its own tile set therefore pairs them up: whatever tile the
Genesis draws in a cell should carry the pixels DOS draws in that cell.

Matching is on PATTERN -- which pixels of a block share a colour -- because
neither side's palette survives the trip: the DOS art is 8-bit VGA and the
Genesis tiles are 4bpp with a runtime palette.

Usage:
    wallpair.py <dos.png> <port.png> [deco]
"""

import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import genwall

REPO = Path(__file__).resolve().parent.parent
TILES = REPO / "extracted/images/8X8D1"
SETS = (0x0918A8, 0x0EBE89)          # what set 3, the dock's, installs


def sig_rgb(block):
    flat = [tuple(p) for row in block for p in row]
    seen, out = {}, []
    for c in flat:
        if c not in seen:
            seen[c] = len(seen)
        out.append(seen[c])
    return tuple(out)


def sig_4bpp(t):
    px = []
    for y in range(8):
        for x in range(8):
            b = t[y * 4 + x // 2]
            px.append((b >> 4) if x % 2 == 0 else (b & 0xF))
    seen, out = {}, []
    for v in px:
        if v not in seen:
            seen[v] = len(seen)
        out.append(seen[v])
    return tuple(out)


def dos_tiles(deco):
    import numpy as np
    from PIL import Image
    out = {}
    for f in glob.glob(str(TILES / ("%03d_*.png" % deco))):
        n = int(re.search(r"_(\d+)\.png", f).group(1))
        out[n] = np.asarray(Image.open(f).convert("RGB")).astype(int)
    return out


def cells(path, sigs, box, scale=None):
    import numpy as np
    from PIL import Image
    im = Image.open(path)
    if scale and im.size != scale:
        im = im.resize(scale, Image.NEAREST)
    a = np.asarray(im.convert("RGB")).astype(int)
    x0, y0, x1, y1 = box
    out = {}
    for cy in range(y0, y1 - 7, 8):
        for cx in range(x0, x1 - 7, 8):
            got = sigs.get(sig_rgb(a[cy:cy + 8, cx:cx + 8]))
            if got is not None:
                out[((cx - x0) // 8, (cy - y0) // 8)] = got
    return out


def pair(dos_png, port_png, deco=5, rom=None):
    rom = (rom or REPO / "roms/matrix_play.gen").read_bytes() \
        if not isinstance(rom, bytes) else rom
    art = dos_tiles(deco)
    dsig = {}
    for n, t in art.items():
        dsig.setdefault(sig_rgb(t), n)
    gsig, gtiles = {}, {}
    for addr in SETS:
        tiles, _nt, _raw = genwall.read(rom, addr)
        for i, t in enumerate(tiles):
            gsig.setdefault(sig_4bpp(t), (addr, i))
            gtiles[(addr, i)] = t
    dos = cells(dos_png, dsig, (8, 0, 136, 144), scale=(320, 200))
    port = cells(port_png, gsig, (0, 0, 200, 176))
    pairs = {}
    for cell, gen in port.items():
        if cell in dos:
            pairs.setdefault(gen, {}).setdefault(dos[cell], 0)
            pairs[gen][dos[cell]] += 1
    best = {g: max(v, key=v.get) for g, v in pairs.items()}
    return best, art, gtiles


if __name__ == "__main__":
    best, art, gtiles = pair(sys.argv[1], sys.argv[2],
                             int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    print(f"{len(best)} Genesis tiles paired with Matrix Cubed tiles")
    for (addr, i), d in sorted(best.items())[:20]:
        print(f"  0x{addr:06X} tile {i:3d}  <-  deco tile {d:3d}")

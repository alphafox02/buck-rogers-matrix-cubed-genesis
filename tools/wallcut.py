# SPDX-License-Identifier: MIT
"""
Recover the atlas cut list by matching DOS screenshots against the records.

A WALLDEF1 record is an atlas: the same wall drawn at every view position,
boxes separated by the game's magenta. Which box goes where on screen is
not in the data, but the game will show you -- so read it off screenshots.

For each 8x8 cell of a screenshot's 3D view, find which of the deco's 256
tiles it is. Colour comparison fails, because the extracted tiles carry a
different palette from the frame buffer, so compare PATTERN instead:
reduce a block to which of its pixels share a colour, and match on that.

Then look the resulting rows of tile indices up in the fifteen records. A
row that appears at offsets 75, 82, 89, 96 tells you both the piece's width
-- seven -- and where it lives, and the box follows.

Usage:
    wallcut.py <deco> <screenshot.png> [more.png ...]
"""

import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dax

REPO = Path(__file__).resolve().parent.parent
TILES = REPO / "extracted/images/8X8D1"
WALLDEF = REPO / "dos_game/matrix/WALLDEF1.DAX"
RECORD = 156
CODES = 15
PANE = (8, 0, 136, 144)          # the 3D view, in 320x200 coordinates
MINRUN = 4                       # shorter runs match by accident
MINDISTINCT = 3                  # and a run of one repeated tile matches
                                 # everywhere, so insist on some variety


def signature(block):
    """Colour-independent: which pixels share a colour."""
    flat = [tuple(px) for row in block for px in row]
    seen, out = {}, []
    for c in flat:
        if c not in seen:
            seen[c] = len(seen)
        out.append(seen[c])
    return tuple(out)


def tile_signatures(deco):
    import numpy as np
    from PIL import Image
    out = {}
    for f in glob.glob(str(TILES / ("%03d_*.png" % deco))):
        n = int(re.search(r"_(\d+)\.png", f).group(1))
        sig = signature(np.asarray(Image.open(f).convert("RGB")).astype(int))
        out.setdefault(sig, n)
    return out


def screen_tiles(path, sigs):
    """{(cell x, cell y): tile index} for one screenshot's view pane."""
    import numpy as np
    from PIL import Image
    im = Image.open(path)
    if im.size != (320, 200):
        im = im.resize((320, 200), Image.NEAREST)
    a = np.asarray(im.convert("RGB")).astype(int)
    x0, y0, x1, y1 = PANE
    out = {}
    for cy in range(y0, y1 - 7, 8):
        for cx in range(x0, x1 - 7, 8):
            got = sigs.get(signature(a[cy:cy + 8, cx:cx + 8]))
            if got is not None:
                out[(cx // 8, cy // 8)] = got
    return out


def boxes(deco, shots):
    """[(code, offset, width, screen x, screen y)] for every run located."""
    block = dax.load(WALLDEF)[deco]
    recs = [block[i * RECORD:(i + 1) * RECORD] for i in range(CODES)]
    sigs = tile_signatures(deco)
    found = []
    for path in shots:
        cells = screen_tiles(path, sigs)
        rows = {}
        for (cx, cy), v in cells.items():
            rows.setdefault(cy, {})[cx] = v
        for cy, row in rows.items():
            xs = sorted(row)
            run, start = [], None
            for i, x in enumerate(xs + [None]):
                if x is not None and (start is None or x == xs[i - 1] + 1):
                    if start is None:
                        start = x
                    run.append(row[x])
                    continue
                # A screen row runs across the back wall AND the side walls
                # either side of it, and only the middle is one box, so try
                # every window of the run rather than the whole thing.
                best = None
                for w in range(len(run), MINRUN - 1, -1):
                    for i in range(0, len(run) - w + 1):
                        window = run[i:i + w]
                        if len(set(window)) < MINDISTINCT:
                            continue
                        seq = bytes(window)
                        for code, rec in enumerate(recs):
                            off = rec.find(seq)
                            if off >= 0:
                                best = (code + 1, off, w, start + i, cy)
                                break
                        if best:
                            break
                    if best:
                        break
                if best:
                    found.append(best)
                run, start = ([row[x]], x) if x is not None else ([], None)
    return found


if __name__ == "__main__":
    deco = int(sys.argv[1])
    got = boxes(deco, sys.argv[2:])
    print(f"deco {deco}: {len(got)} runs located")
    for code, off, w, sx, sy in sorted(set(got)):
        print(f"  code {code:2d}  atlas[{off:3d}:{off+w:3d}] w={w}  "
              f"screen cell ({sx},{sy})")

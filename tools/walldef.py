"""
Decode Matrix Cubed's 3D wall art.

Each area names a deco, and the deco is two archives that share a block
numbering -- 1, 3, 5, ... 19, 22, the ids `LOAD_AREA_DECO` passes:

    8X8D1.DAX    256 8x8 tiles, the pieces the walls are drawn from
    WALLDEF1.DAX fifteen 156-byte records, one per wall code 1-15

A record is 156 tile indices laid out **12 wide by 13 tall** -- the 96x104
3D viewport -- with tile 0x01 transparent. That shape is what makes it
readable: the transparent cut-outs are identical in every one of the
fifteen records, because the silhouette of a wall in perspective does not
depend on what the wall is made of, and only the texture changes between
codes. The dock's deco 5 gives brick, dark panelling, rock, and at codes 7
and 8 a bank of screens and readouts, which is the courtesy console the
scripts talk to.

An earlier note here had LOTEK.DAX and HITEK.DAX down as the source. They
are not: their records index past what those archives hold, while every
value here lands inside the 256 tiles 8X8D1 carries -- 254 of the 256 are
used across one deco.

Usage:
    walldef.py [deco] [out.png]
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
WIDE, TALL = 12, 13          # the viewport, in tiles
RECORD = WIDE * TALL         # 156 bytes
CODES = 15
BLANK = 0x01                 # the transparent tile


def tiles(deco):
    """{index: 8x8 image} for one deco's tile set."""
    from PIL import Image
    out = {}
    for f in glob.glob(str(TILES / ("%03d_*.png" % deco))):
        n = int(re.search(r"_(\d+)\.png", f).group(1))
        out[n] = Image.open(f).convert("RGB")
    return out


def records(deco, path=None):
    """[bytes] -- one 156-byte record per wall code."""
    block = dax.load(path or WALLDEF)[deco]
    return [block[i * RECORD:(i + 1) * RECORD] for i in range(CODES)]


def render(deco, code=None, path=None):
    """One wall code as an image, or all fifteen on a sheet."""
    from PIL import Image
    art, recs = tiles(deco), records(deco, path)
    def one(rec):
        im = Image.new("RGB", (WIDE * 8, TALL * 8), (255, 0, 255))
        for i, v in enumerate(rec):
            if v != BLANK and v in art:
                im.paste(art[v], ((i % WIDE) * 8, (i // WIDE) * 8))
        return im
    if code is not None:
        return one(recs[code])
    cols = 5
    sheet = Image.new("RGB", (cols * (WIDE * 8 + 4),
                              ((CODES + cols - 1) // cols) * (TALL * 8 + 4)),
                      (20, 20, 20))
    for i, rec in enumerate(recs):
        sheet.paste(one(rec), ((i % cols) * (WIDE * 8 + 4),
                               (i // cols) * (TALL * 8 + 4)))
    return sheet


if __name__ == "__main__":
    deco = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    out = sys.argv[2] if len(sys.argv) > 2 else "walls.png"
    im = render(deco)
    im.resize((im.width * 2, im.height * 2)).save(out)
    print(f"deco {deco}: {CODES} wall codes, {WIDE}x{TALL} tiles each -> {out}")

"""
Show what Matrix Cubed's creatures will look like on the Genesis.

Their combat sprites are 24x24, which is exactly the 3x3 tiles a Genesis
figure frame uses, so they need no scaling. The only thing that changes is
the palette: a figure blob carries none of its own, so the art has to be
quantised to whatever the engine supplies.

That palette is in `figure_palette.json`, read off the hardware by
tools/palette_probe.py rather than found in the ROM -- fifteen colours plus
transparent.

Usage:
    preview_creatures.py [block ...]        # CPIC1 block numbers
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dax
import inject_portrait as ip
from PIL import Image

PALETTE = [tuple(c) for c in
           json.load(open(Path(__file__).resolve().parent / "figure_palette.json"))]
ZOOM = 5


def convert(img):
    out = Image.new("RGB", img.size)
    src, dst = img.convert("RGB").load(), out.load()
    for y in range(img.height):
        for x in range(img.width):
            dst[x, y] = min(PALETTE, key=lambda c: ip.distance(src[x, y], c))
    return out


def main():
    blocks = [int(a, 0) for a in sys.argv[1:]]
    if not blocks:
        blocks = sorted(dax.load(REPO / "dos_game/matrix/CPIC1.DAX"))[:10]
    rows = []
    for n in blocks:
        try:
            s = ip.sources(f"CPIC1/{n:03d}")[0].convert("RGB")
        except Exception:
            continue
        rows.append((n, s, convert(s)))
    if not rows:
        sys.exit("nothing to preview")
    w = rows[0][1].width * ZOOM
    sheet = Image.new("RGB", (w * len(rows), rows[0][1].height * ZOOM * 2 + 8),
                      (30, 30, 40))
    for i, (_n, s, o) in enumerate(rows):
        sheet.paste(s.resize((w, w), Image.NEAREST), (i * w, 0))
        sheet.paste(o.resize((w, w), Image.NEAREST), (i * w, w + 8))
    out = REPO / "art_preview" / "creatures_preview.png"
    out.parent.mkdir(exist_ok=True)
    sheet.save(out)
    print(f"{len(rows)} creatures -> {out}  (DOS above, Genesis palette below)")


if __name__ == "__main__":
    main()

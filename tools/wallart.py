"""
Decode Matrix Cubed's wall pieces, the art the port does not yet carry.

The DOS game draws its corridors from two sets of 24x24 pieces:

    LOTEK.DAX   52 pieces, low technology -- the mining warrens and such
    HITEK.DAX   53 pieces, high technology -- stations and their interiors

and `WALLDEF1.DAX` says which pieces a given wall code draws: 2340 bytes
per deco, fifteen 156-byte records, one per wall code 1-15, eleven decos
whose ids match the `LOAD_AREA_DECO` arguments the scenario issues.

Rendering HITEK shows what the codes mean. Most pieces are structural --
runs of corridor wall, corners, edges -- and then:

    39, 40   a desk and a work station
    41       a lit terminal: the courtesy console
    42, 43   doors
    46, 47   a staircase

which matches what the scripts say when the party faces them: "THE STAIRS
LEAD ...", "THIS DOOR IS SEALED SHUT", "THE COMPUTER COMES TO LIFE".

The port still draws Countdown's own pieces, which is why an exit reads as
blank wall. Injecting these is the outstanding job; this is its input side.

Usage:
    wallart.py [LOTEK|HITEK] [out.png]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dax
import gbimage

REPO = Path(__file__).resolve().parent.parent
SETS = ("LOTEK", "HITEK")


def pieces(name):
    """[(index, width, height, pixels)] for one wall set."""
    blob = dax.load(str(REPO / "dos_game/matrix" / f"{name}.DAX"))[1]
    return list(gbimage.frames(blob)), gbimage.palette(blob)


def sheet(name, out, zoom=2, cols=13):
    from PIL import Image, ImageDraw
    frames, pal = pieces(name)
    cw = 24 * zoom
    rows = (len(frames) + cols - 1) // cols
    img = Image.new("RGB", (cols * cw, rows * (cw + 12)), (22, 22, 30))
    d = ImageDraw.Draw(img)
    for i, (_idx, w, h, pix) in enumerate(frames):
        im = Image.frombytes("P", (w, h), bytes(pix))
        im.putpalette(pal)
        x, y = (i % cols) * cw, (i // cols) * (cw + 12)
        img.paste(im.convert("RGB").resize((cw, cw), Image.NEAREST), (x, y))
        d.text((x + 2, y + cw), str(i), fill=(235, 235, 140))
    img.save(out)
    return len(frames)


if __name__ == "__main__":
    which = sys.argv[1].upper() if len(sys.argv) > 1 else "HITEK"
    out = sys.argv[2] if len(sys.argv) > 2 else f"{which.lower()}_pieces.png"
    n = sheet(which, out)
    print(f"  {which}: {n} pieces -> {out}")

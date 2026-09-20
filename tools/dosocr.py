"""Read the text off a DOSBox screen.

Driving the DOS original by keystroke only gets so far: to compare it with
the port square by square we have to know what it just said, and screenshots
answer that only if a person looks at them.

The game's own 8x8 font is block 201 of 8X8D1.DAX, so the glyphs need no
guessing. It is stored rotated: index 0 is '@', so index = (ord(c) - 0x40)
& 0x3F, and only capitals exist -- the game shouts everything.

DOSBox renders the 320x200 mode at 640x400, so a character cell is 16x16 on
screen and halves back to the font's 8x8. The cell grid is found rather than
assumed: score all sixteen phases by how much ink lands inside a cell.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dax

REPO = Path(__file__).resolve().parent.parent
FONT_DAX, FONT_BLOCK = "dos_game/matrix/8X8D1.DAX", 201
CELL = 16                                 # on screen, after DOSBox doubles


def glyphs(path=None):
    """{character: 8x8 bool array} for every glyph the font holds."""
    raw = dax.load(path or REPO / FONT_DAX)[FONT_BLOCK]
    out = {}
    for c in range(0x20, 0x60):
        i = (c - 0x40) & 0x3F
        bits = np.array([[bool(raw[i * 8 + y] & (0x80 >> x)) for x in range(8)]
                         for y in range(8)])
        out[chr(c)] = bits
    return out


_GLYPHS = None


def read(im, box=None, threshold=60):
    """Every line of text on the screen, as (y, x, string)."""
    global _GLYPHS
    if _GLYPHS is None:
        _GLYPHS = glyphs()
    a = np.asarray(im.convert("L")).astype(int)
    x0, y0, x1, y1 = box or (0, 0, a.shape[1], a.shape[0])
    ink = a[y0:y1, x0:x1] > threshold
    if not ink.any():
        return []
    # Halve back to the mode's own resolution before matching.
    small = ink[::2, ::2]
    phase_y = max(range(8), key=lambda p: _score(small, p, axis=0))
    phase_x = max(range(8), key=lambda p: _score(small, p, axis=1))
    order = sorted(_GLYPHS.items(), key=lambda kv: -kv[1].sum())
    out = []
    for cy in range(phase_y, small.shape[0] - 7, 8):
        line, run = [], False
        for cx in range(phase_x, small.shape[1] - 7, 8):
            cell = small[cy:cy + 8, cx:cx + 8]
            ch = " "
            if cell.sum():
                ch = min(order, key=lambda kv: int((kv[1] ^ cell).sum()))[0]
                # Inverse video: the bar is the background, so try again
                # against the complement when the direct match is poor.
                if int((_GLYPHS[ch] ^ cell).sum()) > 12:
                    inv = ~cell
                    alt = min(order, key=lambda kv: int((kv[1] ^ inv).sum()))[0]
                    if int((_GLYPHS[alt] ^ inv).sum()) < int((_GLYPHS[ch] ^ cell).sum()):
                        ch = alt
                run = True
            line.append(ch)
        text = "".join(line).rstrip()
        if run and text.strip():
            out.append((y0 + cy * 2, x0 + phase_x * 2, text))
    return out


def _score(small, phase, axis):
    """How well a phase lines the ink up on eight-pixel cells."""
    ink = small.any(axis=1 - axis)
    idx = np.where(ink)[0]
    return int((((idx - phase) % 8) < 7).sum())


def text(im, **kw):
    return "\n".join(t for _y, _x, t in read(im, **kw))


if __name__ == "__main__":
    from PIL import Image
    for p in sys.argv[1:]:
        print(f"=== {p}")
        for y, x, t in read(Image.open(p)):
            print(f"{y:3d},{x:3d}  {t}")

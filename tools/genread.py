# SPDX-License-Identifier: MIT
"""
Read the Genesis screen as text, off the tilemap rather than the pixels.

The port has to be driven the way the DOS original now is -- answer what is
on screen instead of pressing buttons and hoping -- and pixel OCR is the
wrong tool for a machine whose text is already a grid of tile indices.

The engine draws every character as one tile, and the encoding is flat:

    tile = 0x06 + (ord(c) - 0x20)

so space is 0x06, '0' is 0x16 and 'A' is 0x27. Confirmed against a screen
reading "A ROUND OF DRINKS WILL COST 0 CREDITS." / "PRESS C TO CONTINUE".

A second copy of the font sits at 0x700, used for the leading letter of a
menu option -- the key you would press -- so a reader that does not fold
0x700 back loses the first letter of every choice and reports LINIC, EPOT,
RAINING. Which option is selected is in the palette bits rather than the
tile: the chosen one is drawn in palette 3 and the rest in palette 2, while
the leading letter of every option is palette 0 whichever it is.

That leading letter is what makes multi-word options readable. Splitting
"BUY DRINKS TALK WAIT EXIT" on spaces gives five options where there are
four, and every cursor move after that lands one place out. Splitting where
palette drops back to 0 gives BUY DRINKS / TALK / WAIT / EXIT.

Dialogue, prompts and menus live on the WINDOW plane, which is why reading
plane A finds only scenery. Its base comes out of VDP register 3.

A savestate carries the lot: GENPLUS-GX puts VRAM at 0x12424 and the VDP
register file at 0x22525.
"""

import struct

VRAM = 0x12424
REGS = 0x22525
FIRST = 0x06                # the tile for space
ALT = 0x700                 # the second font, for a menu option's key
CHOSEN = 0x6000             # palette 3: the option under the cursor
COLS, ROWS = 40, 28


def planes(state: bytes):
    """{name: base address} for the three tilemaps, from the VDP registers."""
    r = state[REGS:REGS + 24]
    return {"A": (r[2] & 0x38) << 10,
            "B": (r[4] & 0x07) << 13,
            "W": (r[3] & 0x3E) << 10}


def rows(state: bytes, plane="W"):
    """The screen as one string per row, spaces where nothing is drawn."""
    vram = state[VRAM:VRAM + 0x10000]
    base = planes(state)[plane]
    out = []
    for row in range(ROWS):
        line = []
        for col in range(COLS):
            tile = struct.unpack_from(">H", vram,
                                      base + (row * 64 + col) * 2)[0] & 0x7FF
            if tile >= ALT:
                tile -= ALT
            ch = tile - FIRST + 0x20
            # The engine shouts everything, so a lowercase result is never
            # a letter -- it is one of the window frame's own tiles, which
            # land in the same numeric range and otherwise read as jljjjl.
            line.append(chr(ch) if 0x20 <= ch < 0x7F
                        and not ("a" <= chr(ch) <= "z") else " ")
        out.append("".join(line).rstrip())
    return out


def text(state: bytes, plane="W"):
    return "\n".join(r for r in rows(state, plane) if r.strip())


def cells(state: bytes, plane="W"):
    """Raw nametable entries, so a caller can see palette as well as tile."""
    vram = state[VRAM:VRAM + 0x10000]
    base = planes(state)[plane]
    return [[struct.unpack_from(">H", vram, base + (r * 64 + c) * 2)[0]
             for c in range(COLS)] for r in range(ROWS)]


def choices(state: bytes, row=None):
    """[(option, selected)] for the horizontal menu, in cursor order.

    `row` defaults to the last row carrying any text, which is where the
    engine puts the prompt.
    """
    grid, lines = cells(state), rows(state)
    if row is None:
        lit = [r for r, line in enumerate(lines) if line.strip()]
        if not lit:
            return []
        row = lit[-1]
    # Prose is drawn entirely in palette 0. A menu is not: its options are
    # palette 2 or 3 with only their leading letter back at 0. Without that
    # check a sentence splits at every letter, and "NOT EVERYONE BELIEVES
    # IN YOUR CAUSE." reads as thirty separate choices.
    if not any(grid[row][c] & 0x6000 in (0x4000, CHOSEN)
               for c in range(COLS)):
        return []
    out, word, pals = [], "", []
    for c, ch in enumerate(lines[row] + " "):
        pal = grid[row][c] & 0x6000 if c < COLS else None
        starts = pal == 0 and ch.isalnum()
        if starts and word:
            out.append((word, CHOSEN in pals))
            word, pals = "", []
        if ch == " " and not word:
            continue
        if ch == " " and pal is None:
            break
        word += ch
        pals.append(pal)
    if word.strip():
        out.append((word.strip(), CHOSEN in pals))
    return [(w.strip(), s) for w, s in out if w.strip()]


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        print(f"=== {path}")
        print(text(open(path, "rb").read()))

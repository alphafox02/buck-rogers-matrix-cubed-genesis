"""
Put Matrix Cubed's credits screen back into the port's intro.

DOS shows one screen of names between the Buck Rogers logo and the Matrix
Cubed card: CREATED BY: SSI SPECIAL PROJECTS TEAM, then programming, encounter
code, graphic arts, music and playtest. The Genesis port has no such screen.
Its ROM does carry a credits roll -- a bytecode at 0x00632E played from around
0x0061C4 -- but that one names *Countdown to Doomsday's* team, and nothing in
either ROM appears to reach it.

The text is taken from GAME.OVR, where DOS keeps it as plain ASCII, and the
glyphs from the DOS game's own 8x8 font (block 201 of 8X8D1.DAX, the one
tools/dosocr.py reads screens with), so the screen is drawn in the typeface the
original used.

**Where the code goes.** The intro at 0x012FC draws a screen, then stamps six
overlays telling Countdown's story. `tools/trim_intro.py` cuts that off by
replacing `moveq #$6,d2 / moveq #$11,d3` at 0x001408 with `bra.w $15f0`, which
leaves everything from 0x00140C to the exit at 0x0015F0 -- 484 bytes -- as dead
code. That is enough room for a routine that loads one more screen and shows
it, and it is inside the checksummed first megabyte, so the sum is repaired
afterwards. No free space exists within a `bra.w` of the intro, so reusing the
dead region is what makes this a patch rather than a relocation.

**The container** is the one the other intro screens use: a tile count, a
nametable length, a flag word of 4 meaning "a 16-word palette follows", the
nametable, the tiles, then the palette. 40x28 cells, the full screen.

Usage:
    introcredits.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dosocr
import integrity
import lzw_encode

FREE, FREE_LIMIT = 0x1B4300, 0x1B5000   # measured free, and clear of the rest
PATCH = 0x00140C                        # the dead overlay code
TRIMMED = 0x001408                      # trim_intro's `bra.w $15f0`
EXIT = 0x0015F0
COLS, ROWS = 40, 28

# Index 0 is TRANSPARENT on a Genesis plane, so a background of 0 lets the
# Matrix Cubed card show through and the credits come out unreadable on top of
# it. The background here is a non-zero index that happens to be black.
BG, INK, DIM = 15, 1, 2
PALETTE = {BG: (0, 0, 0), INK: (0, 7, 0), DIM: (2, 6, 2)}   # 3-bit RGB

# Straight out of dos_game/matrix/GAME.OVR. `True` marks a bright line.
LINES = [
    ("CREATED BY: SSI SPECIAL PROJECTS TEAM", True),
    ("", False),
    ("GAME DEVELOPMENT:      PROGRAMMING:", True),
    ("RHONDA GILBERT          RUSS BROWN", False),
    ("                        KERRY BONIN", False),
    ("", False),
    ("ENCOUNTER CODE:", True),
    ("DAVE SHELLEY           GRAPHIC ARTS:", None),
    ("CHRIS CARR              LAURA BOWEN", False),
    ("TOM ONO                 FRED BUTTS", False),
    ("KEN EKLUND              MAURINE STARKEY", False),
    ("TONY VAN                MIKE PROVENZA", False),
    ("GARY SHOCKLEY           MARK JOHNSON", False),
    ("CYNTHIA HUANG           CYRUS LUM", False),
    ("ADRAGON DEMELLO         SUSAN MANLEY", False),
    ("", False),
    ("MUSIC: RALPH THOMAS & THE FAT MAN", True),
    ("", False),
    ("PLAYTEST: JOHN BOOCKHOLDT, AL BROWN,", True),
    ("GLEN CURETON, MIKE GILMARTIN,", False),
    ("CYRUS HARRIS, ROB LUPO, SEAN HOUSE,", False),
    ("JOHN KIRK, ALAN MARENCO, BRIAN LOWE,", False),
    ("JEFF SHOTWELL, LARRY WEBBER,", False),
    ("CHRIS WARSHAUER, JAMES YOUNG", False),
]

# A line marked None is mixed: a name on the left, a heading on the right,
# which is how DOS sets "DAVE SHELLEY  GRAPHIC ARTS:". The split is the run of
# spaces before the heading.
TOP = 2          # leave a couple of rows above


def tiles_and_map():
    """Every cell of the screen, as a tile list and a nametable."""
    glyphs = dosocr.glyphs()
    cache, tiles = {}, []

    def tile_for(ch, colour):
        key = (ch, colour)
        if key in cache:
            return cache[key]
        bits = glyphs.get(ch)
        t = bytearray([(BG << 4) | BG] * 32)
        if bits is not None:
            for y in range(8):
                for x in range(0, 8, 2):
                    hi = colour if bits[y][x] else BG
                    lo = colour if bits[y][x + 1] else BG
                    t[y * 4 + x // 2] = (hi << 4) | lo
        cache[key] = len(tiles)
        tiles.append(bytes(t))
        return cache[key]

    # The loader draws tile index + 1: a ramp screen, row r filled with tile
    # r, comes back showing B on row 0 and C on row 1. So the first tile in
    # the list is never reachable, and one throwaway goes in front of it.
    tiles.append(bytes([(BG << 4) | BG] * 32))
    blank = tile_for(" ", INK)
    nt = [blank] * (COLS * ROWS)
    for r, (text, bright) in enumerate(LINES):
        row = TOP + r
        if row >= ROWS:
            raise SystemExit(f"credits need {TOP + len(LINES)} rows, screen has {ROWS}")
        split = None
        if bright is None:                  # name left, heading right
            split = text.rstrip().rfind("  ") + 2
        for c, ch in enumerate(text[:COLS]):
            if bright is None:
                colour = INK if c >= split else DIM
            else:
                colour = INK if bright else DIM
            nt[row * COLS + c] = tile_for(ch.upper(), colour)
    return tiles, nt


def container(tiles, nt):
    out = bytearray()
    out += struct.pack(">HHH", len(tiles), len(nt) * 2, 4)
    # Every intro screen's nametable words carry 0x4000 -- palette line 2 --
    # and the palette the container ships is loaded into that line. Writing
    # line 0 instead leaves the text drawn in whatever the previous screen
    # happened to leave there, which is unreadable rather than merely wrong.
    # ...and the word written is one BELOW the tile wanted, because the
    # loader adds one. With the throwaway tile in front, every real tile sits
    # at index >= 1, so `t - 1` is always in range.
    for t in nt:
        out += struct.pack(">H", 0x4000 | (t - 1))
    for t in tiles:
        out += t
    for i in range(16):
        r, g, b = PALETTE.get(i, (0, 0, 0))
        out += struct.pack(">H", (b << 9) | (g << 5) | (r << 1))
    return bytes(out)


def routine(addr):
    """Load the screen and show it, mirroring the EA logo's own draw exactly.

    Copying the register setup was not optional. The first version set only
    d0-d5 and the three 0xB5xx words, and blastem stopped with "machine freeze
    due to write to address DFFFFE" -- the blitter writing into unmapped space
    because the plane setup at 0x08594 had never run. The EA logo at 0x001338
    is the working template and this follows it instruction for instruction:

        move.w #$8000, d6 / moveq #2, d7 / bsr $8594     plane setup
        d0-d5, $b510, $b512, $b50e                       blit parameters
        jsr $95be                                        draw
        move.b #$f, $9bbc.w                              view mode
        jsr $860e                                        show
    """
    code = bytearray()

    def at():
        return PATCH + len(code)

    # The intro has already loaded three screens into -4/-8/-0xC(a6), and the
    # graphics allocator is a STACK: 0x0978C refuses anything but the newest
    # and calls the "Graphics freed out of order" handler. Loading a fourth
    # over the -8 slot leaks that handle and makes the exit's frees illegal,
    # which is what froze the machine. So the two screens this port never
    # draws -- Countdown's subtitle banners -- are freed first, newest first,
    # and the credits screen takes the slot that is now genuinely free.
    code += b"\x41\xee\xff\xf4"                          # lea -$c(a6), a0
    code += b"\x4e\xb9" + struct.pack(">I", 0x9784)      # jsr $9784  free
    code += b"\x41\xee\xff\xf8"                          # lea -$8(a6), a0
    code += b"\x4e\xb9" + struct.pack(">I", 0x9784)      # jsr $9784  free
    code += b"\x41\xf9" + struct.pack(">I", addr)        # lea.l addr, a0
    code += b"\x4e\xb9" + struct.pack(">I", 0x9DD4)      # jsr  $9dd4
    code += b"\x2d\x48\xff\xf8"                          # move.l a0, -8(a6)
    code += b"\x3c\x3c\x80\x00"                          # move.w #$8000, d6
    code += b"\x7e\x02"                                  # moveq  #2, d7
    here = at()
    code += b"\x61\x00" + struct.pack(">h", 0x8594 - (here + 2))
    code += b"\x70\x00\x72\x02\x74\x00\x76\x00"          # d0=0 d1=2 d2=0 d3=0
    code += b"\x78\x28\x7a\x1c"                          # d4=40 d5=28
    code += b"\x31\xfc\xff\xff\xb5\x10"                  # move.w #$ffff,$b510
    code += b"\x42\x78\xb5\x12"                          # clr.w $b512
    code += b"\x42\x78\xb5\x0e"                          # clr.w $b50e
    code += b"\x20\x6e\xff\xf8"                          # movea.l -8(a6), a0
    code += b"\x4e\xb9" + struct.pack(">I", 0x95BE)      # jsr  $95be  draw
    code += b"\x11\xfc\x00\x0f\xb9\xbc"                  # move.b #$f,$9bbc.w
    code += b"\x4e\xb9" + struct.pack(">I", 0x860E)      # jsr  $860e  show
    code += b"\x30\x3c\x01\x68"                          # move.w #$168, d0
    code += b"\x4e\xb9" + struct.pack(">I", 0x75FA)      # jsr  $75fa  hold
    here = at()
    code += b"\x60\x00" + struct.pack(">h", EXIT - (here + 2))
    return bytes(code)


def build(rom: bytes):
    tiles, nt = tiles_and_map()
    blob = container(tiles, nt)
    packed = lzw_encode.compress(blob)
    if FREE + len(packed) > FREE_LIMIT:
        raise SystemExit(f"credits screen is {len(packed)} bytes, "
                         f"only {FREE_LIMIT - FREE} free")
    out = bytearray(rom)
    out[FREE:FREE + len(packed)] = packed
    code = routine(FREE)
    if PATCH + len(code) > EXIT:
        raise SystemExit("routine does not fit the dead region")
    out[PATCH:PATCH + len(code)] = code
    out[TRIMMED:TRIMMED + 4] = b"\x4e\x71\x4e\x71"       # nop nop -> fall through
    print(f"  screen: {len(tiles)} tiles, {len(nt)} cells, {len(blob)} bytes"
          f" -> {len(packed)} packed at 0x{FREE:06X}")
    print(f"  routine: {len(code)} bytes at 0x{PATCH:06X}"
          f" (dead region is {EXIT - PATCH} bytes)")
    print(f"  0x{TRIMMED:06X}: trim_intro's bra.w replaced with nop nop")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = integrity.repair(build(src.read_bytes()))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

# SPDX-License-Identifier: MIT
"""
Put Matrix Cubed's own credits into the port.

The Genesis ROM rolls credits for *Countdown to Doomsday* -- Tony Van, Bret
Berry, Michael McNally, and EA's producer. Those are the people who built the
engine, and they should stay. But the game being played is Matrix Cubed, and
the thirty-odd people who made it were nowhere in the ROM.

DOS keeps its credits as plain text in GAME.OVR, behind a "Credits" menu
option, under CREATED BY: SSI SPECIAL PROJECTS TEAM.

The Genesis roll is a small bytecode, read by the player at 0x0061C4
(`lea.l $632e.l, a2`) and dispatched at 0x0061CA:

    0xFC <pic>   start, set the picture
    0xFF <pic>   end the page, wait, show the next picture
    0xFE         the next string is a HEADING, drawn at column 0 in 0xE000
    <string>     otherwise a NAME, drawn at column 3 in 0xC000
    0xFD         end of the roll

Strings are NUL-terminated. Nine pages in the original, never more than nine
lines on one, which is what the layout below keeps to.

This writes Matrix Cubed's team first and then carries the Countdown credits
over verbatim behind a page that says what they are for, so both sets of
authors are named. The new roll does not fit in the original 799 bytes, so it
goes to free space and the `lea` operand is repointed.

Usage:
    credits.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integrity

STREAM = 0x00632E           # where the shipped roll starts
LEA_OPERAND = 0x0061C6      # the operand of `lea.l $632e.l, a2`
FREE, FREE_LIMIT = 0x1B2100, 0x1B4000
HEADING, PAGE, START, END = 0xFE, 0xFF, 0xFC, 0xFD

# Read out of dos_game/matrix/GAME.OVR, which stores them as plain text.
PAGES = [
    (0x32, [("h", "Created By"), ("n", "SSI Special Projects Team"),
            ("h", "Programming"), ("n", "Rhonda Gilbert"),
            ("n", "Russ Brown"), ("n", "Kerry Bonin")]),
    (0x43, [("h", "Encounter Code"), ("n", "Dave Shelley"),
            ("h", "Music"), ("n", "Ralph Thomas"), ("n", "The Fat Man")]),
    (0x54, [("h", "Graphic Arts"), ("n", "Chris Carr"), ("n", "Laura Bowen"),
            ("n", "Tom Ono"), ("n", "Fred Butts"), ("n", "Ken Eklund"),
            ("n", "Maurine Starkey")]),
    (0x42, [("h", "Graphic Arts"), ("n", "Tony Van"), ("n", "Mike Provenza"),
            ("n", "Gary Shockley"), ("n", "Mark Johnson"),
            ("n", "Cynthia Huang"), ("n", "Cyrus Lum"),
            ("n", "Adragon Demello"), ("n", "Susan Manley")]),
    (0x34, [("h", "Playtest"), ("n", "John Boockholdt"), ("n", "Al Brown"),
            ("n", "Glen Cureton"), ("n", "Mike Gilmartin"),
            ("n", "Cyrus Harris"), ("n", "Rob Lupo"), ("n", "Sean House")]),
    (0x57, [("h", "Playtest"), ("n", "John Kirk"), ("n", "Alan Marenco"),
            ("n", "Brian Lowe"), ("n", "Jeff Shotwell"),
            ("n", "Larry Webber"), ("n", "Chris Warshauer"),
            ("n", "James Young")]),
    (0x4F, [("h", "Genesis Engine From"), ("n", "Buck Rogers"),
            ("n", "Countdown to Doomsday")]),
]

MAX_LINES = 9


def read_original(rom: bytes):
    """The shipped roll, as (picture, [(kind, text)]) pages."""
    a = STREAM
    pages, cur, pic = [], [], None
    while True:
        b = rom[a]
        if b == END:
            break
        if b in (START, PAGE):
            if cur:
                pages.append((pic, cur))
                cur = []
            pic = rom[a + 1]
            a += 2
            continue
        kind = "n"
        if b == HEADING:
            kind = "h"
            a += 1
        end = rom.index(b"\x00", a)
        cur.append((kind, rom[a:end].decode("latin1")))
        a = end + 1
    if cur:
        pages.append((pic, cur))
    return pages


def encode(pages):
    out = bytearray()
    for i, (pic, rows) in enumerate(pages):
        if len(rows) > MAX_LINES:
            raise SystemExit(f"page {i + 1} has {len(rows)} lines, max {MAX_LINES}")
        out.append(START if i == 0 else PAGE)
        out.append(pic)
        for kind, text in rows:
            if kind == "h":
                out.append(HEADING)
            out += text.encode("latin1") + b"\x00"
    out.append(END)
    return bytes(out)


def build(rom: bytes):
    original = read_original(rom)
    pages = list(PAGES) + original
    blob = encode(pages)
    if FREE + len(blob) > FREE_LIMIT:
        raise SystemExit("out of free space for the credits")
    out = bytearray(rom)
    out[FREE:FREE + len(blob)] = blob
    struct.pack_into(">I", out, LEA_OPERAND, FREE)
    print(f"  {len(PAGES)} new pages + {len(original)} carried over"
          f" = {len(pages)} pages, {len(blob)} bytes at 0x{FREE:06X}")
    print(f"  lea operand at 0x{LEA_OPERAND:06X} repointed from 0x{STREAM:06X}")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = integrity.repair(build(src.read_bytes()))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

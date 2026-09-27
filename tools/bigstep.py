# SPDX-License-Identifier: MIT
"""
Step a 48x48 creature square to square instead of sliding it.

A figure that is standing is plane A tiles and a 48x48 draws correctly as six
rows by six. A figure that is MOVING is hardware sprites, and a Genesis sprite
stops at 4x4 tiles -- so 24x24 is one sprite and slides perfectly, while 48x48
has to be four, each drawing a different quarter of the art. Getting four
sprites to exist works (see tools/bigslide.py); getting them to draw four
different quarters does not, because the quarter belongs to the figure RECORD
an entry points at rather than to the entry, and every way of giving them one
record each so far makes the creature vanish.

So skip the glide. `0x0FA52` is the whole slide -- take the figure off the
board, blit its cells into VRAM, walk the sprites 24 pixels at a time -- and
returning from it immediately leaves the caller at `0x0F95C` to commit the new
square and the board to redraw the creature there as tiles. A 48x48 steps from
one square to the next rather than gliding between them, and it is a dinosaur
the whole way instead of a 24x24 corner of one.

Every other size is untouched and still slides.

a2 is the creature's record on entry -- `0x0FA5A` reads `$23(a2)` as the first
thing the routine does -- so the size is one compare away, before the `link`.

Usage:
    bigstep.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

BIG = 4
SLIDE = 0x0FA52
SLIDE_END = 0x0FA5A           # past the prologue, which the block reproduces
SLIDE_STOCK = bytes.fromhex("4e56fff448e73f30")

NEW = 0x0F1F20                # free: combatgap.py's block ends by 0x0F1F18
NEW_LIMIT = 0x0F1FD8
FILLER = (0x00, 0xFF)


def block() -> bytes:
    # The test comes before the prologue, so the early exit is a plain `rts`
    # with nothing of the routine's own on the stack yet.
    code = bytes.fromhex("0c2a") + struct.pack(">H", BIG) + bytes.fromhex("0023")
    code += bytes((0x66, 0x02))            # bne  -> slide as usual
    code += bytes.fromhex("4e75")          # rts  -- a 48x48 does not slide
    code += SLIDE_STOCK                    # link.w / movem.l, verbatim
    return code + b"\x4e\xf9" + struct.pack(">I", SLIDE_END)


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    if bytes(rom[SLIDE:SLIDE + len(SLIDE_STOCK)]) != SLIDE_STOCK:
        raise SystemExit(f"0x{SLIDE:05X} is not the slide's prologue: "
                         f"{bytes(rom[SLIDE:SLIDE + len(SLIDE_STOCK)]).hex()}")
    code = block()
    if NEW + len(code) > NEW_LIMIT:
        raise SystemExit("the new block does not fit")
    if any(b not in FILLER for b in rom[NEW:NEW + len(code)]):
        raise SystemExit(f"0x{NEW:06X}+{len(code)} is not free")
    rom[NEW:NEW + len(code)] = code
    room = SLIDE_END - SLIDE
    rom[SLIDE:SLIDE_END] = (b"\x4e\xf9" + struct.pack(">I", NEW)
                            + b"\x4e\x71" * ((room - 6) // 2))
    print(f"  0x{SLIDE:05X} slide: jmp 0x{NEW:06X} ({len(code)} bytes), "
          f"rejoins 0x{SLIDE_END:05X}")
    print("  a 48x48 creature steps square to square; every other size slides")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

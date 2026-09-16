"""
Make a missing art resource degrade instead of stopping the game.

The chunked decompressor at 0x09BB6 loads a resource in `chunk`-sized
pieces and counts down the bytes it has left:

    09C26: sub.w  d3, d6        ; remaining -= chunk
    09C28: bmi.w  $9cf6         ; overshot -> "loadpieces error 1"
    09C2C: bne.b  $9c10

Overshooting means the pointer it was handed was never a resource. That
happens whenever Matrix Cubed names a figure, wall set or piece id the
Countdown cartridge does not carry: the directory search at 0x099CC runs
off its end into 0x099F6, which loads a pointer that is not one, and the
decompressor reads nonsense.

Countdown can afford to treat that as fatal because its own data is always
complete. A transplant cannot -- every id that has no counterpart yet turns
into a dead run, and there are hundreds of them across four resource
spaces. Guarding each space one at a time chased the same crash through
several rebuilds.

So the branch is pointed at the routine's own clean exit instead:

    09CE4: clr.b    $b4cb.w
    09CE8: movea.l  a2, a0
    09CEA: move.l   -$10(a6), d0
    09CEE: movem.l  (a7)+, d2-d6/a2-a3
    09CF2: unlk     a6
    09CF4: rts

which unwinds the stack frame properly and returns. The picture simply does
not appear. One byte: the branch displacement, 0xCC to 0xBA.

A second site needs the same treatment, and play found it: the figure
directory search itself.

    099C6: lea.l   $9a14.l, a1     ; the combat figure directory
    099CC: move.b  $4(a1), d1      ; this record's id
    099D0: bmi.b   $99f6           ; ran off the end -> "LoadFigure error"
    099D2: cmp.b   d0, d1
    099D6: addq.l  #$8, a1         ; next record
    099F0: movem.l (a7)+, d3-d4    ; the clean exit
    099F4: rts

Patching only the decompressor left this one reachable: SPRITE_START with
an id Countdown has no figure for walks the directory to its terminator and
prints the error before any decompression is attempted. Block 17 does
exactly that -- `SPRITE_START 255, 0, 1, 0` right after the Sun King papers
-- and it ended the run. Pointing the bmi at 0x099F0 makes the sprite simply
not appear.

This is a safety net, not a licence to leave ids unmapped -- a substituted
sprite is better than a blank one, and docs/art_todo.md still tracks what
needs injecting. It exists so that one unmapped id cannot cost a whole
play session.

Usage:
    softfail.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

BRANCH = 0x09C2A          # displacement word of the bmi.w at 0x09C28
ERROR_TARGET = 0x09CF6
CLEAN_EXIT = 0x09CE4

# The figure-directory search. A short branch, so the displacement is the
# second byte of the instruction itself.
FIG_BRANCH = 0x099D0
FIG_ERROR = 0x099F6
FIG_CLEAN = 0x099F0


def _short_branch(rom, at, want_error, clean, what):
    if rom[at] != 0x6B:
        raise SystemExit(f"expected bmi.b at 0x{at:05X}, found {rom[at]:02X}")
    have = rom[at + 1]
    if at + 2 + have != want_error:
        raise SystemExit(f"{what} branch goes to 0x{at + 2 + have:05X}, "
                         f"not the error site 0x{want_error:05X}")
    new = clean - (at + 2)
    if not 0 < new < 0x80:
        raise SystemExit(f"{what} clean exit is out of short-branch range")
    rom[at + 1] = new
    print(f"  0x{at:05X} bmi.b: 0x{want_error:05X} -> 0x{clean:05X} "
          f"(displacement 0x{have:02X} -> 0x{new:02X})  [{what}]")


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    if rom[BRANCH - 2] != 0x6B or rom[BRANCH - 1] != 0x00:
        raise SystemExit(f"expected bmi.w at 0x{BRANCH - 2:05X}, found "
                         f"{rom[BRANCH - 2]:02X}{rom[BRANCH - 1]:02X}")
    have = struct.unpack_from(">h", rom, BRANCH)[0]
    if BRANCH + have != ERROR_TARGET:
        raise SystemExit(f"branch goes to 0x{BRANCH + have:05X}, not the error site")
    struct.pack_into(">h", rom, BRANCH, CLEAN_EXIT - BRANCH)
    print(f"  0x{BRANCH - 2:05X} bmi.w: 0x{ERROR_TARGET:05X} -> 0x{CLEAN_EXIT:05X} "
          f"(displacement 0x{have:04X} -> 0x{CLEAN_EXIT - BRANCH:04X})")
    _short_branch(rom, FIG_BRANCH, FIG_ERROR, FIG_CLEAN, "LoadFigure")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = apply(src.read_bytes())
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

# SPDX-License-Identifier: MIT
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
-- and it ended the run.

Sending the branch to the clean exit at 0x099F0 was tried and was WORSE. It
skips `movea.l (a1), a0`, so the caller carries on with whatever a0 held and
writes through it: the machine froze on a write to 0xDFFFFE. A loader that
returns without loading is not a safe failure when its caller expects a
pointer back.

So the error path is replaced with what the picture loader at 0x0B7D6
already does on a miss -- substitute a default and retry. The twelve bytes
of `lea` plus `jsr` become

    099F6: lea.l  $9a14.l, a1      ; back to the first record
    099FC: bra.b  $99da            ; and load that one

Record 0 is a real figure (pointer 0x075E10, chunk 0x12), so a0 comes back
valid and the decompressor is handed actual data. The wrong character
appears rather than none, which is the same bargain the art substitution
makes everywhere else.

A third site draws the junk on the floor that a play session kept
photographing. The resource dispatcher splits on bit 7 of the id:

    099BC: bclr.b #$7, d0      ; strip bit 7 and test it
    099C0: bne.b  $9964        ; it was set -> the figure-sheet path
    ...
    09968: ext.w  d0
    09974: asl.w  #$2, d0
    09976: lea.l  $998c.l, a0  ; a table of exactly 12 entries
    0997C: movea.l (a0, d0.w), a0
    09982: bsr.w  $9bb6        ; decompress whatever that was

`bclr` leaves d0 as `id & 0x7F`, so 0 to 127, and nothing checks it against
the twelve entries at 0x0998C-0x099BC. Any id at or above 0x80 whose low
bits reach 12 reads a pointer from past the end of the table -- the figure
directory, and then the code after it -- and decompresses it into the
figure buffer. Countdown never does this; Matrix Cubed's ids are not the
same ids.

The `ext.w d0` and `movea.l a3, a1` at 0x09968 become a call to a helper
written over the freed "LoadFigure error" string, which does the same two
things with a clamp between them.

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

# The figure-directory search: its error path, the directory it walks, and
# the instruction that loads a record once one is found.
FIG_ERROR = 0x099F6
FIG_ERROR_END = 0x09A02          # where "LoadFigure error" itself starts
FIG_DIRECTORY = 0x09A14
FIG_LOAD = 0x099DA
FIG_ORIGINAL = bytes.fromhex("41f900009a024eb9000132a6")


def _figure_fallback(rom):
    at = FIG_ERROR
    if bytes(rom[at:FIG_ERROR_END]) != FIG_ORIGINAL:
        raise SystemExit(f"0x{at:05X} is not the LoadFigure error path")
    patch = bytearray()
    patch += b"\x43\xf9" + struct.pack(">I", FIG_DIRECTORY)   # lea.l dir, a1
    disp = FIG_LOAD - (at + len(patch) + 2)
    if not -0x80 <= disp < 0:
        raise SystemExit("figure load is out of short-branch range")
    patch += bytes([0x60, disp & 0xFF])                        # bra.b load
    patch += b"\x4e\x71" * ((FIG_ERROR_END - at - len(patch)) // 2)
    rom[at:at + len(patch)] = patch
    print(f"  0x{at:05X} LoadFigure error -> fall back to figure record 0 "
          f"(lea 0x{FIG_DIRECTORY:05X}, bra 0x{FIG_LOAD:05X})")


# The figure-sheet path, its 12-entry table, and the freed error string the
# bounds check is written into.
SHEET_CALL = 0x09968
SHEET_ORIGINAL = bytes.fromhex("4880224b")     # ext.w d0 / movea.l a3, a1
SHEET_ENTRIES = 12
HELPER = 0x09A02
HELPER_LIMIT = 0x09A14                         # the figure directory starts here


def _sheet_bounds(rom):
    if bytes(rom[SHEET_CALL:SHEET_CALL + 4]) != SHEET_ORIGINAL:
        raise SystemExit(f"0x{SHEET_CALL:05X} is not the figure-sheet entry")
    helper = (b"\x48\x80"                       # ext.w   d0
              + b"\x0c\x40" + struct.pack(">H", SHEET_ENTRIES)   # cmpi.w #12, d0
              + b"\x6d\x02"                     # blt.b   .ok
              + b"\x70\x00"                     # moveq   #0, d0
              + b"\x22\x4b"                     # .ok: movea.l a3, a1
              + b"\x4e\x75")                    # rts
    if HELPER + len(helper) > HELPER_LIMIT:
        raise SystemExit("bounds-check helper does not fit before the directory")
    rom[HELPER:HELPER + len(helper)] = helper
    disp = HELPER - (SHEET_CALL + 2)
    rom[SHEET_CALL:SHEET_CALL + 4] = b"\x61\x00" + struct.pack(">h", disp)
    print(f"  0x{SHEET_CALL:05X} figure-sheet index now clamped to "
          f"{SHEET_ENTRIES} entries (helper at 0x{HELPER:05X}, {len(helper)} bytes)")


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
    _figure_fallback(rom)
    _sheet_bounds(rom)
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = apply(src.read_bytes())
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

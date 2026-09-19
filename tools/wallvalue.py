"""
Refresh the facing wall value when the party TURNS, not only when it moves.

`0x9AF8` holds the wall code in the direction the party faces -- the thing
DOS calls `0xC04E` and reads in 80 places across Matrix Cubed to ask what
kind of place it is standing in. The engine recomputes it at `0x04228`, and
the movement path does so as soon as the new position is written:

    054CE  move.b -$1B(a6), $9AF7.w     ; X
    054D4  move.b -$19(a6), $9AF6.w     ; Y
    054DA  bsr.w  $4210
    054DE  bsr.w  $4228                 ; <- recompute 0x9AF8
    054E2  bsr.w  $4E00

The turn path writes the facing and then jumps straight PAST it:

    0543C  move.b d0, $9AFA.w           ; facing
    05440  moveq  #$2, d0
    05444  bsr.w  $5566
    05448  bra.w  $54E2                 ; <- skips the recompute

so after a turn -- and after a step, because the facing is written after the
position -- `0x9AF8` still describes the direction the party was looking a
moment ago. Every script gate on it is answered one action late, which is
why walking up to a wall did nothing and walking into it a second time
worked.

The fix is the branch displacement: land on `0x054DE` instead of `0x054E2`
so the turn path recomputes too. Two bytes.

Usage:
    wallvalue.py <in.gen> <out.gen>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

SITE = 0x0544A            # the displacement of the bra.w at 0x05448
BEFORE = bytes([0x00, 0x98])      # -> 0x054E2, past the recompute
AFTER = bytes([0x00, 0x94])       # -> 0x054DE, through it


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    if bytes(rom[SITE:SITE + 2]) != BEFORE:
        raise SystemExit(
            f"0x{SITE:05X} is {bytes(rom[SITE:SITE+2]).hex()}, expected "
            f"{BEFORE.hex()}; this is not the ROM the patch was measured on")
    rom[SITE:SITE + 2] = AFTER
    print(f"  turn path now recomputes 0x9AF8 (0x{SITE:05X}: "
          f"{BEFORE.hex()} -> {AFTER.hex()})")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

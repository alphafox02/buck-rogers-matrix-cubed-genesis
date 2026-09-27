# SPDX-License-Identifier: MIT
"""
Raise the engine's 64-monster ceiling.

Countdown ships 54 creatures and Matrix Cubed has 36 the cartridge has never
seen -- Purge commandos, the Amalthean and gang rosters, the Jovian dragon,
Killer Kane. Fitting them needs 90 slots.

The 64 is not a format limit. The loader reads the count out of the stream
itself and only the buffer it reads ids into is fixed:

    048E8: link.w  a6, #$ffbe     ; 66 bytes of locals
    04900: bsr.w   $9ed8          ; read the count word to a6-2
    04906: subi.l  #$40, d0       ; ids go to a6-0x40, so 64 of them
    04916: bsr.w   $9ed8          ; read `count` id bytes there
    0491A: lea.l   -$40(a6), a0   ; and the search walks them from there
    0491E: move.w  -$2(a6), d1    ; count, from the data

So the ceiling is a stack frame. Moving the buffer to a6-0x80 and growing
the frame to match gives 128, which is room for both rosters and some left
over. The count word stays at a6-2, clear of ids as long as the count is
under 126.

Three operands change and nothing else: the stream is reached from exactly
one place in the ROM, `lea.l $9e77c.l, a0` at 0x048F2.

This only raises the ceiling. Filling the new slots means adding monster
records and combat figures, which is separate work.

Usage:
    monstercap.py <in.gen> <out.gen> [slots]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

LINK = 0x048E8          # link.w a6, #imm
SUBI = 0x04906          # subi.l #imm, d0
LEA = 0x0491A           # lea.l -imm(a6), a0

ORIGINAL = {LINK: "4e56ffbe", SUBI: "048000000040", LEA: "41eeffc0"}
OLD_SLOTS = 0x40


def apply(rom: bytes, slots=0x80) -> bytes:
    rom = bytearray(rom)
    for at, want in ORIGINAL.items():
        got = bytes(rom[at:at + len(want) // 2]).hex()
        if got != want:
            raise SystemExit(f"0x{at:05X} is not what monstercap expects: "
                             f"{got}, wanted {want}")
    if slots % 2 or not 0x40 <= slots <= 0x7E + 2:
        raise SystemExit("slots must be even and leave the count word room")

    # The frame has to cover the buffer plus the two-byte count above it.
    struct.pack_into(">h", rom, LINK + 2, -(slots + 2))
    struct.pack_into(">I", rom, SUBI + 2, slots)
    struct.pack_into(">h", rom, LEA + 2, -slots)
    print(f"  monster ceiling {OLD_SLOTS} -> {slots}: "
          f"link -{slots + 2}, buffer at a6-0x{slots:02X}")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    slots = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x80
    out = apply(src.read_bytes(), slots)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

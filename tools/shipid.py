# SPDX-License-Identifier: MIT
"""
Matrix Cubed numbers its ships from one; the Genesis table is zero based.

`SPACE_COMBAT`'s first argument chooses the enemy ship. The transpiler only
renames the opcode, so the number goes straight through -- and the two games
do not agree on where the roster starts.

The rosters themselves are identical, which is what makes the off-by-one
visible rather than merely suspected:

    Countdown strings 100-104   RAM SCOUT  RAM MEDIUM  RAM HEAVY
                                PIRATE MEDIUM  MERCURIAN MEDIUM
    Matrix Cubed block 19       1 RAM SCOUT   2 RAM MED.   3 RAM HVY.
                                4 PIR. MED.   5 MER. MED.

Same five ships in the same order, but Matrix Cubed compares its variable
against 1 to 5 while the Genesis engine indexes a table whose first entry is
the scout. The stats settle it. Records are 34 bytes at `0x17722`, read by
`0x19C60` as `id * 0x22`, and the first four fields are 16-bit:

    index 0    200   65   160   150     RAM SCOUT, the weakest
    index 1    600  150   450   450     RAM MEDIUM
    index 2   2000  500  1500  1500     RAM HEAVY, the strongest
    index 3    400  100   300   300     PIRATE MEDIUM
    index 4    800  200   600   600     MERCURIAN MEDIUM
    index 5    600  150   450   450     the player's own ship

Zero based that sequence reads correctly -- scout weakest, heavy strongest --
and index 5 matches what block 18's REPAIR writes for the player's own hull
(600) and fuel (450), which is why `0x17874` fetches type 5 for the player.
One based it does not: the heavy cruiser would be weaker than the scout.

So every encounter is shifted one slot up. A RAM MEDIUM fights as a RAM HEAVY
at 2000/500/1500/1500 against the player's 1650, and a MERCURIAN MEDIUM fights
as a copy of the player's own ship. Reported from play as "is this a thing
where the enemy ships are way way more powerful than mine".

The correction cannot be made in the transpiler, because the argument is
usually a variable -- block 19 passes `[0x4C93]`, filled by `RANDOM 7` and
folded back into 1-5 -- so there is no constant to adjust. It is made here
instead, where the handler stores the argument:

    03788  bsr.w   $404a          ; fetch the argument
    0378C  move.b  d0, $9924.w    ; the enemy ship id

Those eight bytes become a jump to a block that fetches the argument, takes
one off when it is not already zero, and stores it. Zero is left alone so a
script that already counts from zero -- Countdown's own, and the developer
block -- is not pushed below the table.

Usage:
    shipid.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

SITE = 0x03788
SITE_END = 0x03790
STOCK = bytes.fromhex("610008c011c09924")

FETCH = 0x0404A             # the argument reader
SHIP_ID = 0xFF9924          # where the handler keeps the enemy ship

NEW = 0x0F1F60              # free: combatgap.py's block ends by 0x0F1F5E
NEW_LIMIT = 0x0F2000        # music starts at 0x0F2004


def block() -> bytes:
    sid = struct.pack(">H", SHIP_ID & 0xFFFF)
    code = b"\x4e\xb9" + struct.pack(">I", FETCH)   #  0 jsr    $404a
    code += bytes.fromhex("4a00")                   #  6 tst.b  d0
    code += bytes((0x67, 0x02))                     #  8 beq.b  .store
    code += bytes.fromhex("5300")                   # 10 subq.b #1, d0
    code += bytes.fromhex("11c0") + sid             # 12 .store move.b d0, id
    return code + b"\x4e\xf9" + struct.pack(">I", SITE_END)     # 16 back


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    if bytes(rom[SITE:SITE + len(STOCK)]) != STOCK:
        raise SystemExit(f"0x{SITE:05X} is not the ship-id store: "
                         f"{bytes(rom[SITE:SITE + len(STOCK)]).hex()}")
    code = block()
    if NEW + len(code) > NEW_LIMIT:
        raise SystemExit("the new block does not fit")
    if any(rom[NEW:NEW + len(code)]):
        raise SystemExit(f"0x{NEW:05X}+{len(code)} is not free: "
                         f"{bytes(rom[NEW:NEW + len(code)]).hex()[:32]}...")
    rom[NEW:NEW + len(code)] = code
    patch = b"\x4e\xf9" + struct.pack(">I", NEW)
    rom[SITE:SITE + len(patch)] = patch
    # Pad the two bytes the jump does not use with NOP rather than leaving
    # halves of the old instruction there. Nothing reaches them -- the jump is
    # unconditional -- but a stray 0x4E4E decodes as TRAP #14, and an
    # unreachable trap is a bad thing to leave in a ROM.
    for k in range(SITE + len(patch), SITE_END, 2):
        struct.pack_into(">H", rom, k, 0x4E71)     # nop
    print(f"  0x{SITE:05X} enemy ship id: jmp 0x{NEW:06X} ({len(code)} bytes), "
          f"rejoins 0x{SITE_END:05X}")
    print("  a ship id of 1-5 becomes 0-4, so RAM HEAVY is the heavy cruiser "
          "and not the medium")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

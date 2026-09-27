"""
Never start a combat with the two sides standing on top of each other.

The Genesis engine works the starting gap out from the map rather than from
the script. `0x035BE` counts the open squares ahead of the party with
`0x04DAA` -- which stops counting at two -- takes the smaller of that and the
number the script asked for in `[0x9DB7]`, and then `0x03652` takes one off
what is left. `0x15056` copies the result into `[0xD4FE]`, and `0x14844`
multiplies the placement offsets by it, so a gap of zero puts the monsters on
the squares the party is standing on.

Read live through the demo's fight, that chain gives:

    96.67s  party (10,1) facing 3   gap 2
    98.33s  party (10,1) facing 3   gap 1
    99.20s  party (10,1) facing 3   gap 0      <- and it is still 0 at COMBAT

so both sides arrive nose to nose, nobody walks anywhere, and the Venus
Dinosaur never leaves its square. A play session put it as "the fight has the
people all together instead of apart like in the dos game so they can walk
towards one another -- i only ever see the t rex in one spot".

Forcing the gap and looking at the board gives 1 = still crowded, 2 = the DOS
picture, two sides with room between them, 3 = the monsters placed off the
visible board. So this raises a gap of ZERO to two and leaves every other
value alone: where the engine found room it already knows better than a
constant would, and where it found none the alternative is an overlap.

The ambush case at `0x1505C`, which forces the gap to 1 when `[0xD8CC]` is
set, still runs after this and still wins.

Usage:
    combatgap.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

SITE = 0x15056
SITE_END = 0x1505C
STOCK = bytes.fromhex("11f89db6d4fe")

NEW = 0x0F1F00              # free: bigplacement.py's block ends by 0x0F1E9A
NEW_LIMIT = 0x0F1FD0        # music starts at 0x0F2004

GAP = 0xFFD4FE              # the placement multiplier
DISTANCE = 0xFF9DB6         # min(open squares ahead, what the script asked for)
FLOOR = 2                   # squares, when the engine found none at all


def block() -> bytes:
    code = bytes.fromhex("11f8") + struct.pack(">H", DISTANCE & 0xFFFF) \
         + struct.pack(">H", GAP & 0xFFFF)                    # the stock copy
    code += bytes.fromhex("4a38") + struct.pack(">H", GAP & 0xFFFF)   # tst.b
    code += bytes((0x66, 0x06))                                       # bne out
    code += bytes.fromhex("11fc00") + bytes((FLOOR,)) \
          + struct.pack(">H", GAP & 0xFFFF)                    # move.b #2, gap
    return code + b"\x4e\xf9" + struct.pack(">I", SITE_END)


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    if bytes(rom[SITE:SITE + len(STOCK)]) != STOCK:
        raise SystemExit(f"0x{SITE:05X} is not the gap copy: "
                         f"{bytes(rom[SITE:SITE + len(STOCK)]).hex()}")
    code = block()
    if NEW + len(code) > NEW_LIMIT:
        raise SystemExit("the new block does not fit")
    if any(rom[NEW:NEW + len(code)]):
        raise SystemExit(f"0x{NEW:05X}+{len(code)} is not free: "
                         f"{bytes(rom[NEW:NEW + len(code)]).hex()[:32]}...")
    rom[NEW:NEW + len(code)] = code
    rom[SITE:SITE_END] = b"\x4e\xf9" + struct.pack(">I", NEW)
    print(f"  0x{SITE:05X} combat gap: jmp 0x{NEW:06X} ({len(code)} bytes), "
          f"rejoins 0x{SITE_END:05X}")
    print(f"  a gap of none becomes {FLOOR} squares, so the two sides start apart")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

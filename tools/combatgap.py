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
visible board.

The first version of this raised a gap of zero to two unconditionally, and
that was wrong for the reason the paragraph above should have made obvious:
`[0x9DB6]` is already the measured open space, so a gap of zero can mean "the
engine found ONE open square" -- and two squares of separation then puts the
monsters a square past the open ground, through whatever wall stopped the
count. Reported from play as "the enemies are too far outside the map, they
are on the other side of a wall".

So the gap is raised to `min([0x9DB6], FLOOR)` instead. Where the map has room
for two that is still two, the DOS picture; where it has room for one it is
one, crowded but on the board; where it has room for none it stays zero,
because an overlap is at least inside the map.

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

# 0x0F1F00 held the first, shorter version of this block. bigstep.py's block
# sits at 0x0F1F20, immediately after it, so the longer one written here does
# not fit there -- the free-space guard caught that rather than letting it
# overwrite a shipped patch. 0x0F1F38 is clear from the end of bigstep's block
# to the music at 0x0F2004.
NEW = 0x0F1F38
NEW_LIMIT = 0x0F2000

GAP = 0xFFD4FE              # the placement multiplier
DISTANCE = 0xFF9DB6         # min(open squares ahead, what the script asked for)
FLOOR = 2                   # the most separation to ask for, never more
                            # than the map actually has room for


def block() -> bytes:
    """gap = stock; if it came out zero, gap = min(open squares ahead, FLOOR).

    No register is touched -- every step is memory to memory or an immediate
    compare -- because what sits in d0 at 0x15056 belongs to the caller.
    """
    d = struct.pack(">H", DISTANCE & 0xFFFF)
    g = struct.pack(">H", GAP & 0xFFFF)
    code = bytes.fromhex("11f8") + d + g            #  0 the stock copy
    code += bytes.fromhex("4a38") + g               #  6 tst.b  gap
    code += bytes((0x66, 0x14))                     # 10 bne    out
    code += bytes.fromhex("11f8") + d + g           # 12 gap = open squares
    code += bytes.fromhex("0c38") + bytes((0, FLOOR)) + g   # 18 cmpi.b #F, gap
    code += bytes((0x63, 0x06))                     # 24 bls    out
    code += bytes.fromhex("11fc") + bytes((0, FLOOR)) + g   # 26 gap = FLOOR
    return code + b"\x4e\xf9" + struct.pack(">I", SITE_END)   # 32 out


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
    print(f"  a gap of none becomes min(open squares ahead, {FLOOR}), "
          f"so the sides start apart without leaving the map")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

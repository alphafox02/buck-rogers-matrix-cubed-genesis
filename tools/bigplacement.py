"""
Stop a 48x48 creature being placed on top of somebody.

`bigcreature.py` added the 48x48 size class and taught the board to draw it,
mark its four squares and move it. What it missed is the routine that CHOOSES
a square, at `0x14840`. That one stashes the creature's size at `-$202(a6)`
(`0x148AA`, which bigcreature's notes dismiss as "no branch, needs nothing"),
and then branches on it two hundred bytes later:

    1490E  move.b -$202(a6), d0
    14912  cmp.b  #$2, d0        24x48: also test the cell one row down  (+$15)
    14916  bne.b  $14934
    14934  cmp.b  #$3, d0        48x24: also test the cell one col right (+$1)
    14938  bne.b  $14952         anything else: ACCEPT, no extra test at all

So a 48x48 creature is placed having tested only its anchor square. The other
three may already hold somebody, and then a party member is standing inside
it -- correctly hidden, because the board's sprites are already depth sorted
by y (see the note in docs/re_notes.md). A play session put it plainly: "you
can't even see Buck here at the start of the fight."

This adds the size 4 case: all three extra squares, each tested exactly the
way the stock code tests its one, rejecting on bit 7 (occupied) or on terrain
`0x144EA` returns 4 or worse. Nobody ends up inside the creature, and because
only the four squares it really covers are refused, a character can still
stand on any of the eight around it and swing.

DOS agrees: a capture of the original shows the Venus Dinosaur with two
figures beside it and no overlap anywhere.

No bounds check on the three extra reads, which matches what the stock size 2
and size 3 cases do at the edges of the 21x21 board.

Usage:
    bigplacement.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integrity

NEW = 0x0F1E00              # free: bigcreature.py's blocks end by 0x0F1D4C
#
# That figure is checked, not remembered. Adding a fifth block to
# bigcreature.py pushed its cursor from 0x0F1CD6 to 0x0F1D02, straight over
# the front of this one, and the ROM booted and then sat on the intro --
# a collision this far from either tool's own output is not something a
# build log makes obvious. Both tools now refuse to write over a byte that
# is not already zero, so the next one fails loudly instead.
NEW_LIMIT = 0x0F1FD0        # music starts at 0x0F2004

HOOK = 0x14934              # cmp.b #$3, d0 / bne.b $14952
HOOK_WAS = bytes.fromhex("b03c00036618")
ACCEPT = 0x14952            # write the square and mark it
REJECT = 0x14970            # moveq #$0, d6 -- this square will not do
TERRAIN = 0x144EA           # cell byte in d0 -> terrain cost in d0; clobbers a0
CELL = "206efdf4"           # movea.l -$20c(a6), a0 -- the candidate cell
BIG = 4

# The three squares a 48x48 creature covers besides its anchor, as offsets
# into the 21-wide board. Same order bigcreature.py's marker walks them.
EXTRA = (0x01, 0x15, 0x16)


class Asm:
    def __init__(self, at):
        self.at, self.code, self.lab, self.fix = at, bytearray(), {}, []

    def raw(self, h):
        self.code += bytes.fromhex(h.replace(" ", ""))
        return self

    def label(self, n):
        self.lab[n] = self.at + len(self.code)
        return self

    def rel(self, op, name, size=1):
        start = self.at + len(self.code)
        self.code += bytes.fromhex(op)
        self.fix.append((len(self.code), name, size, start + 2))
        self.code += b"\0" * size
        return self

    def jmp(self, addr):
        self.code += b"\x4e\xf9" + struct.pack(">I", addr)
        return self

    def done(self):
        for pos, name, size, pc in self.fix:
            disp = self.lab[name] - pc
            if size == 1:
                if not -128 <= disp <= 127:
                    raise SystemExit(f"{name} out of reach for a byte branch")
                self.code[pos] = disp & 0xFF
            else:
                struct.pack_into(">h", self.code, pos, disp)
        return bytes(self.code)


def test_cell(a, offset):
    """One square, tested the way the stock size 2 and 3 cases test theirs."""
    a.raw(CELL)                                  # movea.l -$20c(a6), a0
    a.raw("1028") .raw(f"{offset:04x}")          # move.b  <off>(a0), d0
    a.rel("6b00", "reject", 2)                   # bmi.w   reject   -- occupied
    a.code += b"\x4e\xb9" + struct.pack(">I", TERRAIN)
    a.raw("0200003f")                            # andi.b  #$3f, d0
    a.raw("b03c0004")                            # cmp.b   #$4, d0
    a.rel("6400", "reject", 2)                   # bcc.w   reject   -- terrain
    return a


def build():
    a = Asm(NEW)
    a.raw("b03c0003")                            # cmp.b #$3, d0
    a.rel("6600", "four", 2)                     # bne.w four
    test_cell(a, 0x01)                           # 48x24, as the stock code did
    a.jmp(ACCEPT)

    a.label("four").raw("b03c").raw(f"{BIG:04x}")   # cmp.b #$4, d0
    a.rel("6600", "accept", 2)                   # bne.w accept -- 24x24 and 24x48
    for off in EXTRA:
        test_cell(a, off)
    a.label("accept").jmp(ACCEPT)
    a.label("reject").jmp(REJECT)
    return a


def patch(rom: bytes):
    out = bytearray(rom)
    if bytes(out[HOOK:HOOK + len(HOOK_WAS)]) != HOOK_WAS:
        raise SystemExit(f"0x{HOOK:05X} is not the size branch this expects "
                         f"({bytes(out[HOOK:HOOK+6]).hex()})")
    a = build()
    code = a.done()
    if NEW + len(code) > NEW_LIMIT:
        raise SystemExit(f"{len(code)} bytes will not fit before 0x{NEW_LIMIT:05X}")
    if any(out[NEW:NEW + len(code)]):
        raise SystemExit(f"0x{NEW:05X}+{len(code)} is not free: "
                         f"{bytes(out[NEW:NEW + len(code)]).hex()[:32]}...")
    out[NEW:NEW + len(code)] = code
    out[HOOK:HOOK + 6] = b"\x4e\xf9" + struct.pack(">I", NEW)
    print(f"  48x48 placement now tests all four squares; {len(code)} bytes at "
          f"0x{NEW:05X}, hook at 0x{HOOK:05X}")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    o = integrity.repair(patch(src.read_bytes()))
    dst.write_bytes(o)
    print(f"checksum {'verifies' if integrity.verify(o) else 'FAILS'}; wrote {dst}")

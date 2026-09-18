"""
Add a 48x48 creature size to the combat board.

The board's creature size comes from the **monster** record's byte 0x23 --
1 for 24x24, 2 for 24x48, 3 for 48x24 -- not from the figure record's class
nibble, which drives some other view. Proved by probing: figure class 0 with
monster size 2 draws tall, figure class 2 with monster size 1 draws small.

Instrumenting every instruction in the ROM that reads `0x23(An)` and then
fighting a genuinely tall creature shows which of them are on the live path:

    0x098B0   +7    extra VRAM slots: large creatures claim one more
    0x0ADA6  +10    the frame shape
    0x142C4  +20    walks every grid square the creature stands on
    0x148AA  +10    stashes the size, no branch, needs nothing
    0x14E86  +60    a "large?" test, already `>= 2`, needs nothing

`0x0ADA6` is the one that matters. It writes rows-1 and cols-1 into
-6(a6) and -8(a6), and a quarter-width into -4(a6):

    size 3   (2, 5)  12     3 rows, 6 cols   48 x 24
    size 2   (5, 2)   6     6 rows, 3 cols   24 x 48
    else     (2, 2)   6     3 rows, 3 cols   24 x 24

So 48x48 is (5, 5) with 12, and a creature that stands on **two squares by
two**. Three blocks are relocated whole into free ROM, each with a size 4
case added and each ending in a jump back to where it left off. None of the
three has a branch entering it from outside, checked across the whole ROM.

Four more sites read the size byte on movement and AI paths that this
encounter never took -- 0x0CC9A, 0x1050C, 0x14552, 0x15DD2 -- and they are
extended too, so a 48x48 creature is not a special case that only looks
right while standing still.

Usage:
    bigcreature.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

NEW = 0x0F1BD8              # 1024 zero bytes; music starts at 0x0F2000
NEW_LIMIT = 0x0F1FD0

BIG = 4                     # the size byte value this adds


class Asm:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.fix = []

    def raw(self, h):
        self.code += bytes.fromhex(h.replace(" ", ""))
        return self

    def br(self, op, label):
        self.fix.append((len(self.code) + 1, label, len(self.code) + 2))
        self.code += bytes((op, 0))
        return self

    def jmp(self, target):
        self.code += b"\x4e\xf9" + struct.pack(">I", target)
        return self

    def label(self, n):
        self.labels[n] = len(self.code)
        return self

    def done(self):
        for slot, name, pc in self.fix:
            d = self.labels[name] - pc
            if not 0 < d < 128:
                raise SystemExit(f"{name}: {d} bytes out of short range")
            self.code[slot] = d
        return bytes(self.code)


# ---- the three live sites -------------------------------------------------

SLOTS = 0x098B0
SLOTS_END = 0x098BC
SLOTS_STOCK = bytes.fromhex("10290023b03c000163025246")

SHAPE = 0x0ADA6
SHAPE_END = 0x0ADFC

SQUARES = 0x142C4
SQUARES_END = 0x142EC

# The frame index, and where a frame starts in the sheet:
#
#     0AE2A: move.b $11(a3), d0   ; animation step
#     0AE2E: asl.b  #$2, d0       ; four units per step
#     0AE60: add.b  d1, d0        ; plus the facing
#     0AE68: add.b  d1, d0        ; twice, if the creature is large
#     0AE74: mulu.w #$12, d0      ; a unit is 18 bytes -- nine cells
#
# A 24x24 frame is nine cells and steps one unit; 24x48 and 48x24 are
# eighteen and step two, which is what the second `add.b` buys. A 48x48
# frame is thirty-six and has to step four, so its index is simply twice
# the large one -- one shift, applied only for size 4.
#
# Size 4 is told apart by the flag at -2(a6): stock writes 0xFF for large
# and 0 for normal, and every test on it in this routine is `tst`/`bne`, so
# writing 1 instead behaves identically everywhere except where this asks
# whether it is negative.
INDEX = 0x0AE6A
INDEX_END = 0x0AE7A
INDEX_STOCK = bytes.fromhex("4880226800024a406706c0fc0012d2c0")


def slots():
    """Large creatures claim one extra VRAM slot; a 2x2 one claims three."""
    a = Asm()
    a.raw("10290023")                      # move.b $23(a1), d0
    a.raw("b03c0001").br(0x63, "out")      # cmp.b #1,d0 / bls out
    a.raw("5246")                          # addq.w #1, d6
    a.raw("b03c").raw(f"{BIG:04x}").br(0x66, "out")   # cmp.b #4,d0 / bne out
    a.raw("5446")                          # addq.w #2, d6   -- three in total
    a.label("out")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", SLOTS_END)


def shape():
    """
    rows-1 into -6(a6), cols-1 into -8(a6), width/4 into -4(a6), and a
    "large" flag into -2(a6). The stock three cases are reproduced exactly;
    size 4 is 6 rows by 6 cols at 48px wide.
    """
    a = Asm()

    def case(rows, cols, quarter, large):
        a.raw("3d7c") .raw(f"{rows:04x}").raw("fffa")   # move.w #r, -$6(a6)
        a.raw("3d7c").raw(f"{cols:04x}").raw("fff8")    # move.w #c, -$8(a6)
        a.raw("3d7c").raw(f"{quarter:04x}").raw("fffc")  # move.w #q, -$4(a6)
        if large == 0xFF:
            a.raw("50eefffe")                           # st.b   -$2(a6)
        elif large:
            a.raw("1d7c").raw(f"00{large:02x}").raw("fffe")  # move.b #n, -$2(a6)
        else:
            a.raw("422efffe")                           # clr.b  -$2(a6)
        a.jmp(SHAPE_END)

    a.raw("10290023")                                   # move.b $23(a1), d0
    a.raw("b03c").raw(f"{BIG:04x}").br(0x66, "n4")
    case(5, 5, 0x0C, 0xFF)                              # 48 x 48
    a.label("n4").raw("b03c0003").br(0x66, "n3")
    case(2, 5, 0x0C, 0xFF)                              # 48 x 24
    a.label("n3").raw("b03c0002").br(0x66, "n2")
    case(5, 2, 0x06, 0xFF)                              # 24 x 48
    a.label("n2")
    case(2, 2, 0x06, 0)                                 # 24 x 24
    return a.done()


def squares():
    """
    Call the visitor once per grid square the creature stands on: one for a
    normal creature, two for a tall or wide one, four for a 2x2.

    `subq` does the dispatch so the tests read the size once: after
    `subq.b #2` the value is -2, -1, 0, 1, 2 for sizes 0 to 4.
    """
    a = Asm()
    a.raw("18290023")                       # move.b $23(a1), d4
    a.raw("7400").raw("142a0012")           # moveq #0,d2 / move.b $12(a2),d2
    a.raw("7600").raw("162a0013")           # moveq #0,d3 / move.b $13(a2),d3
    a.raw("4e93")                           # jsr (a3)          -- (x, y)
    a.raw("5504").br(0x6B, "out")           # subq.b #2,d4 / bmi out
    a.br(0x67, "tall")                      # beq tall          -- size 2
    a.raw("5242").raw("4e93")               # addq.w #1,d2 / jsr (a3)   (x+1, y)
    a.raw("5304").br(0x67, "out")           # subq.b #1,d4 / beq out    -- size 3
    a.raw("5342")                           # subq.w #1,d2      -- back to x
    a.label("tall")
    a.raw("5243").raw("4e93")               # addq.w #1,d3 / jsr (a3)   (x, y+1)
    a.raw("5304").br(0x66, "out")           # subq.b #1,d4 / bne out    -- size 2
    a.raw("5242").raw("4e93")               # addq.w #1,d2 / jsr (a3)   (x+1, y+1)
    a.label("out")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", SQUARES_END)


def index():
    """Double the frame index for size 4, then the stock offset maths."""
    a = Asm()
    # ext.w FIRST. The index is a byte here and `asl.b #2` has already
    # multiplied the animation step by four; doubling it as a byte can reach
    # 0x80, which ext.w then reads as -128 and sends the sheet pointer
    # backwards into whatever precedes it. Widening before doubling keeps it
    # positive.
    #
    # The test is on the shape itself -- six rows AND six columns is 48x48
    # and nothing else -- rather than on the flag byte at -2(a6). There is
    # an `rts` at 0x0AD90 between the `link` at 0x0AD60 and this code, so
    # these are not provably the same stack frame and the flag cannot be
    # trusted across them. The shape words are written by the block this
    # tool already relocated, so they are known good.
    a.raw("4880")                           # ext.w  d0
    a.raw("0c6e0005fffa").br(0x66, "no")    # cmpi.w #5, -$6(a6) / bne no
    a.raw("0c6e0005fff8").br(0x66, "no")    # cmpi.w #5, -$8(a6) / bne no
    a.raw("d040")                           # add.w  d0, d0   -- 48x48
    a.label("no")
    a.raw("22680002")                       # movea.l $2(a0), a1
    a.raw("4a40").br(0x67, "skip")          # tst.w d0 / beq skip
    a.raw("c0fc0012")                       # mulu.w #$12, d0
    a.raw("d2c0")                           # adda.w d0, a1
    a.label("skip")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", INDEX_END)


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    for at, name, stock in ((SLOTS, "slot count", SLOTS_STOCK),):
        if bytes(rom[at:at + len(stock)]) != stock:
            raise SystemExit(f"0x{at:05X} is not the {name}: "
                             f"{bytes(rom[at:at + len(stock)]).hex()}")

    cursor = NEW
    for name, build, site, end in (("slot count", slots, SLOTS, SLOTS_END),
                                   ("frame shape", shape, SHAPE, SHAPE_END),
                                   ("grid squares", squares, SQUARES, SQUARES_END)):
        cursor += cursor & 1
        code = build()
        if cursor + len(code) > NEW_LIMIT:
            raise SystemExit("the new blocks do not fit")
        rom[cursor:cursor + len(code)] = code
        room = end - site
        if room < 6:
            raise SystemExit(f"no room for a jump at 0x{site:05X}")
        rom[site:end] = (b"\x4e\xf9" + struct.pack(">I", cursor)
                         + b"\x4e\x71" * ((room - 6) // 2))
        print(f"  0x{site:05X} {name}: jmp 0x{cursor:06X} ({len(code)} bytes), "
              f"rejoins 0x{end:05X}")
        cursor += len(code)

    print(f"  size {BIG} = 48x48: six rows by six columns, standing on "
          f"two grid squares by two")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

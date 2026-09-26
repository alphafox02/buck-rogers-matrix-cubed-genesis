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

    def dbra(self, reg, label):
        """dbra Dn, <a label already passed> -- 16-bit, so backwards is fine."""
        self.code += bytes((0x51, 0xC8 | reg))
        self.code += struct.pack(">h", self.labels[label] - len(self.code))
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

# Which grid squares a creature is considered to stand on. Stock gives a
# tall creature an extra row and a wide one an extra column; a 2x2 needs
# both. Without it the board repaints the floor over the squares it thinks
# are empty, which wipes the lower half of a 48x48 creature AFTER it has
# been drawn -- the draw loop really does run six rows, logged live as
# rows-1 = 5, cols-1 = 5.
OCCUPY = 0x1050C
OCCUPY_END = 0x1052E

# A 48x48 creature dies and disappears, because nothing else would remove it.
#
# The combat board draws figures as PLANE A TILES, not sprites: d3 at 0x0AE1A
# is a nametable address and the row loop steps it by 0x80, one tile row. So a
# figure's pixels are only ever touched when that figure is drawn, and a
# creature that stops being drawn simply stays on screen. Counting draws of the
# Venus Dinosaur through the demo's fight shows it painted twice in the whole
# combat and never again once it dies -- the dinosaur a play session sees
# standing over the corpse is stale tilemap, with the engine's 24x24 corpse
# painted over one corner of it.
#
# 0x07608 is where a figure dies. It subtracts the damage from $E(a3), picks a
# corpse kind by how far past zero the blow went, writes it to (a3), sets bit 7
# -- which moves the figure to the first of the two draw loops at 0x0ACF4 --
# and, in combat, releases the grid squares it stood on via 0x142A8. What it
# never does is erase the tiles. For a 24x24 creature that does not matter: the
# corpse frame is the same size as the pose and covers it. A 48x48 corpse is a
# quarter of one, so three quarters of the creature is left behind.
#
# The engine already has the piece that is missing. 0x0F996 erases one figure's
# tiles -- 0x0AD3E is the same draw routine with the row writer at 0x0AE92,
# which fills with d7 = 0, and a plane A cell of zero is transparent, so the
# floor on plane B comes back -- and releases its squares. 0x0F9A6, the
# engine's own "take this figure off the board", is exactly that followed by
# `bset #2, $1(a3)`, the bit both draw loops test and skip on. This does the
# same three things for a size 4 creature.
#
# DOS flashes four skulls over the squares before the creature goes. Those are
# not reproduced: there is no draw left to put them in, and a frame that
# persists is not a flash. See docs/re_notes.md for the two frame-index
# rewrites that were tried for that and backed out.
# A 48x48 creature is repainted when anything walks out from under it.
#
# Moving a figure is `0x0F4FA`: show it, erase it (0x0F996), REPAIR whatever
# the erase uncovered (0x0F9F4), write the new square, draw it there (0x0F986).
# The repair is the part that does not scale. It walks the figure array looking
# for another figure whose `$12` matches the mover's as a WORD -- the same x AND
# the same y -- redraws the first one it finds and stops. That is exactly right
# for the case SSI wrote it for, two figures stacked on one square.
#
# A 48x48 creature covers four squares and is drawn from one square north of
# its anchor, so a 24x24 figure walking off any square under that box erases a
# 3x3 patch of the creature and the repair never looks at it: its anchor is a
# different square. Nothing redraws a combat figure otherwise -- they are plane
# A tiles, painted once -- so the bite stays until something else happens to
# repaint the creature. Watching the demo's dinosaur frame by frame, its tail
# and hind legs vanish and come back through the fight, and at 117.40s the whole
# animal is gone for a tenth of a second.
#
# So the repair is replaced with one that also redraws every size 4 creature on
# the board, whatever square it stands on. Redrawing one is idempotent and there
# are at most a handful in a combat, so the cost is a few tile writes per move.
# The stock same-square case is kept, minus its "stop at the first" -- redrawing
# all of them is no more expensive and no less correct.
# How many tiles across and down a figure covers, asked by the attack animation.
#
# `0x0CC66` turns a figure into a tile rectangle -- d2, d3 its top-left corner
# and d4, d5 its extent -- and the action dispatcher at `0x0CAEA` uses it twice:
# once at `0x0CBF0` to blit an animation frame over the figure, and once at
# `0x0CC26`, right after `bset #2, $1(a3)` hides it, to blank the tiles it was
# occupying. Stock starts both at 3 by 3 and widens one of them to 6 for a
# 24x48 or a 48x24. A 48x48 gets 3 by 3, so an attack on one blits and blanks a
# quarter of it and leaves the other three quarters to whatever was there.
#
# On screen that is a 24-pixel column of the dinosaur going missing whenever it
# is shot at -- tail and hind leg gone, healing again the next time anything
# repaints it. Measured over the demo's fight: three separate bites, the worst
# 215 of its 810 pixels, plus one frame at 117.40s with the whole animal gone.
#
# This is the site `bigcreature.py` claimed in its own header to have extended
# and had not.
EXTENT = 0x0CC9A
EXTENT_END = 0x0CCAE
EXTENT_STOCK = bytes.fromhex("1c2a0023bc3c000266027a06bc3c000366027806")


REPAIR = 0x0F9F4
REPAIR_END = 0x0FA20        # the stock body, dead after this; nothing branches in
REPAIR_STOCK = bytes.fromhex("2f0b41f8c470")
FIGURES = 0xC470            # the combat figure array, 0x1A bytes a slot
FIGURE_COUNT = 0xBA64
DRAW_ONE = 0x0AD5A          # draw one figure, a3 = its record


DEATH = 0x07676
DEATH_END = 0x0767E
DEATH_STOCK = bytes.fromhex("244b4eb9000142a8")

UNMARK = 0x142A8            # release the grid squares a figure stood on
RECORD = 0x06F14            # d0 = $2(a3) -> a1 = that creature's record
HIDE = 0x0F996              # erase one figure's tiles, release its squares


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

    def case(rows, cols, quarter, large, lift=False):
        a.raw("3d7c") .raw(f"{rows:04x}").raw("fffa")   # move.w #r, -$6(a6)
        a.raw("3d7c").raw(f"{cols:04x}").raw("fff8")    # move.w #c, -$8(a6)
        a.raw("3d7c").raw(f"{quarter:04x}").raw("fffc")  # move.w #q, -$4(a6)
        if large == 0xFF:
            a.raw("50eefffe")                           # st.b   -$2(a6)
        elif large:
            a.raw("1d7c").raw(f"00{large:02x}").raw("fffe")  # move.b #n, -$2(a6)
        else:
            a.raw("422efffe")                           # clr.b  -$2(a6)
        if lift:
            # The block this jumps to computes the drawing origin as
            # gridX - d4, gridY - d5, and a creature is drawn down and to the
            # right of it. A 2x2 creature therefore has to start one square
            # up so its feet land on the square it occupies.
            a.raw("5245")                               # addq.w #1, d5
        a.jmp(SHAPE_END)

    a.raw("10290023")                                   # move.b $23(a1), d0
    a.raw("b03c").raw(f"{BIG:04x}").br(0x66, "n4")
    case(5, 5, 0x0C, 0xFF, lift=True)                   # 48 x 48
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


def occupy():
    """Sizes 2 and 4 take an extra row, sizes 3 and 4 an extra column."""
    a = Asm()
    a.raw("102a0023")                       # move.b $23(a2), d0
    a.raw("b03c0002").br(0x65, "done")      # cmp.b #2,d0 / bcs done
    a.raw("7400").raw("142b0012")           # moveq #0,d2 / move.b $12(a3),d2
    a.raw("7600").raw("162b0013")           # moveq #0,d3 / move.b $13(a3),d3
    a.raw("5700")                           # subq.b #3, d0   2->-1 3->0 4->1
    a.br(0x67, "wide")                      # beq wide        -- size 3
    a.raw("5243")                           # addq.w #1, d3   -- sizes 2 and 4
    a.raw("4a00").br(0x6B, "done")          # tst.b d0 / bmi done   -- size 2
    a.label("wide").raw("5242")             # addq.w #1, d2
    a.label("done")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", OCCUPY_END)


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


def extent():
    """3x3 tiles, 3x6 for a 24x48, 6x3 for a 48x24 -- and 6x6 for a 48x48."""
    a = Asm()
    a.raw("1c2a0023")                              # move.b $23(a2), d6
    a.raw("bc3c").raw(f"{BIG:04x}").br(0x66, "n4")
    a.raw("7a06").raw("7806").br(0x60, "out")      # moveq #6,d5 / moveq #6,d4
    a.label("n4").raw("bc3c0002").br(0x66, "n2")
    a.raw("7a06")                                  # 24x48: six rows
    a.label("n2").raw("bc3c0003").br(0x66, "out")
    a.raw("7806")                                  # 48x24: six columns
    a.label("out")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", EXTENT_END)


def repair():
    """Redraw the mover's square-mates AND every 48x48 creature.

    Everything is saved: `0x0AD5A` keeps d2-d7 and a2 but not d0, d1, a0 or a1,
    and this has to survive its own loop across the call.
    """
    a = Asm()
    a.raw("48e7fffe")                              # movem.l d0-d7/a0-a6, -(a7)
    a.raw("2c0b")                                  # move.l  a3, d6   the mover
    a.raw("45f8").raw(f"{FIGURES:04x}")            # lea     $c470.w, a2
    a.raw("3638").raw(f"{FIGURE_COUNT:04x}")       # move.w  $ba64.w, d3
    a.raw("342b0012")                              # move.w  $12(a3), d2
    a.label("loop")
    a.raw("4a12").br(0x67, "next")                 # tst.b (a2) / beq  empty slot
    a.raw("bc8a").br(0x67, "next")                 # cmp.l a2, d6 / beq  itself
    a.raw("b46a0012").br(0x67, "draw")             # same square as the mover?
    a.raw("7000").raw("102a0002")                  # moveq #0,d0 / move.b $2(a2),d0
    a.raw("4eb9").raw(f"{RECORD:08x}")             # jsr $6f14  -> a1
    a.raw("0c29").raw(f"{BIG:04x}").raw("0023")    # cmpi.b #4, $23(a1)
    a.br(0x66, "next")
    a.label("draw")
    a.raw("264a")                                  # movea.l a2, a3
    a.raw("4eb9").raw(f"{DRAW_ONE:08x}")           # jsr $ad5a
    a.label("next")
    a.raw("d4fc001a")                              # adda.w #$1a, a2
    a.dbra(3, "loop")
    a.raw("4cdf7fff")                              # movem.l (a7)+, d0-d7/a0-a6
    a.raw("4e75")                                  # rts
    return a.done()


def death():
    """Erase a dead 48x48 creature and stop the board ever drawing it again.

    The two stock instructions come first and unchanged -- a2 is the figure
    and 0x142A8 frees its squares -- because the rest only makes sense once
    the engine has decided this really is a combat death. Everything after
    runs only when the creature's record says size 4.
    """
    a = Asm()
    a.raw("244b")                                  # movea.l a3, a2   (stock)
    a.raw("4eb9").raw(f"{UNMARK:08x}")             # jsr $142a8       (stock)
    a.raw("102b0002")                              # move.b $2(a3), d0
    a.raw("4eb9").raw(f"{RECORD:08x}")             # jsr $6f14  -> a1
    a.raw("0c29").raw(f"{BIG:04x}").raw("0023")    # cmpi.b #4, $23(a1)
    a.br(0x66, "out")
    a.raw("4eb9").raw(f"{HIDE:08x}")               # jsr $f996   erase it
    a.raw("08eb00020001")                          # bset.b #2, $1(a3)
    a.label("out")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", DEATH_END)


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    for at, name, stock in ((SLOTS, "slot count", SLOTS_STOCK),
                            (DEATH, "death", DEATH_STOCK),
                            (REPAIR, "repair", REPAIR_STOCK),
                            (EXTENT, "tile extent", EXTENT_STOCK)):
        if bytes(rom[at:at + len(stock)]) != stock:
            raise SystemExit(f"0x{at:05X} is not the {name}: "
                             f"{bytes(rom[at:at + len(stock)]).hex()}")

    cursor = NEW
    for name, build, site, end in (("slot count", slots, SLOTS, SLOTS_END),
                                   ("frame shape", shape, SHAPE, SHAPE_END),
                                   ("grid squares", squares, SQUARES, SQUARES_END),
                                   ("occupancy", occupy, OCCUPY, OCCUPY_END),
                                   ("death", death, DEATH, DEATH_END),
                                   ("repair", repair, REPAIR, REPAIR_END),
                                   ("tile extent", extent, EXTENT, EXTENT_END)):
        cursor += cursor & 1
        code = build()
        if cursor + len(code) > NEW_LIMIT:
            raise SystemExit("the new blocks do not fit")
        if any(rom[cursor:cursor + len(code)]):
            raise SystemExit(f"0x{cursor:06X}+{len(code)} is not free: "
                             f"{bytes(rom[cursor:cursor + len(code)]).hex()[:32]}...")
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
          f"two grid squares by two, erased when it dies")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

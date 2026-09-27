"""
Slide a 48x48 creature between squares as four sprites, not one.

A combat figure that is STANDING is plane A tiles. A figure that is MOVING is
hardware sprites: `0x0FA52` takes it off the board, blits its cells into VRAM
through the chain at `0xB59A` (which `bigfigures.py` teaches about 48x48), and
walks it to the next square 24 steps at a time. The sprite side of that never
learned the size:

    0FB0E  cmp.b #$2, d7 / addi.w #$18, d1 / movem.w d0-d1, $12(a2)  24x48
    0FB20  cmp.b #$3, d7 / addi.w #$18, d0 / movem.w d0-d1, $12(a2)  48x24
    0FB32  st.b  $1c(a2)                                  everything else: one

so a 48x48 slid as a single 24x24 sprite -- its top-left quadrant, on its own,
crossing the board. A play session called it "jacked up when it moves", and it
only became visible once `combatgap.py` gave the creature room to walk at all.

Genesis sprites stop at 4x4 tiles, so 48x48 is four of them. This writes the
other three positions -- right, below, below-right of the first -- and moves
all four every step. Display entries are 0x12 bytes apart at `[0xB0B4]`, the
same stride `0x0C2xx` uses, and the size is read back from `-1(a6)`, where
`0x0FA5E` already saved it, because d7 is cleared at `0x0FB82` before the
movement loop comes round again.

NOT WIRED INTO THE BUILD. What it does works; what it needs does not exist
yet. Four attempts, each built and watched frame by frame:

  four entries, positions only   the extra sprites appear and move, drawing
                                 whatever quadrant the first one does
  four entries, count raised     `[0xB0B2]` set to 4, at the placement and
                                 again at 0x0F9BE where the two are reserved:
                                 the creature vanishes outright, both times
  two entries, group written     writing the group into byte 0x0A of the
                                 second entry changes nothing
  two entries, side chosen by
  the first entry's group        likewise nothing, and for the same reason

The reason is `0x0C142`. It writes `d7 & $C0` -- the flip bits ALONE -- into
byte 0x0A of an entry and puts the group in `$8(a3)`, the FIGURE record the
entry points at through `$b(a2)`. Two entries pointing at one record therefore
draw one quadrant, and nothing written into the entry survives. Giving a
48x48's four sprites four quadrants means four records, which is a structural
change to how a figure is registered at `0x09870`, not a patch here.

What IS shipped is `bigfigures.py`, which fixes the blit those sprites read
from, so what slides is a clean quarter of the creature instead of a scramble.

Usage:
    bigslide.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

BIG = 4
ENTRY = 0x12                 # bytes per display entry at [0xB0B4]
STEP = 0x18                  # 24 pixels, one square

PLACE = 0x0FB0E
PLACE_END = 0x0FB36
PLACE_STOCK = bytes.fromhex(
    "be3c0002660c0641001848aa000300126016"
    "be3c0003660c0640001848aa00030012600450ea001c")

# How many display entries the engine will read. 0x0F9A6 sets it to two when
# it takes a figure off the board to slide it, and that has to be four before
# anything looks at the list -- setting it later, from the placement block,
# makes the creature disappear entirely.
SLOTS = 0x0F9BE
SLOTS_END = 0x0F9C4
SLOTS_STOCK = bytes.fromhex("31fc0002b0b2")
RECORD = 0x06F14             # d0 = $2(a3) -> a1 = that creature's record

ADVANCE = 0x0FB6C
ADVANCE_END = 0x0FB7E
ADVANCE_STOCK = bytes.fromhex("45f8b0b4d552d76a0002d56a0012d76a0014")

# Two regions, because what is left of the 1024 zero bytes at 0x0F1BD8 is not
# contiguous: bigfigures.py ends at 0x0F1EC4 and combatgap.py sits at 0x0F1F00.
PLACE_NEW = 0x0F1F20         # 184 bytes, up to the music at 0x0F2004
PLACE_NEW_LIMIT = 0x0F1FD8
ADVANCE_NEW = 0x0F1EC4       # 60 bytes, between bigfigures.py and combatgap.py
ADVANCE_NEW_LIMIT = 0x0F1F00
COUNT = 0xB0B2               # how many display entries the engine will read


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

    def label(self, n):
        self.labels[n] = len(self.code)
        return self

    def jmp(self, target):
        self.code += b"\x4e\xf9" + struct.pack(">I", target)
        return self

    def dbra(self, reg, label):
        self.code += bytes((0x51, 0xC8 | reg))
        self.code += struct.pack(">h", self.labels[label] - len(self.code))
        return self

    def done(self):
        for slot, name, pc in self.fix:
            d = self.labels[name] - pc
            if not 0 < d < 128:
                raise SystemExit(f"{name}: {d} bytes out of short range")
            self.code[slot] = d
        return bytes(self.code)


def place():
    """The stock two cases unchanged, and four whole entries for a 48x48.

    d0 and d1 are the first entry's position and stay that way; d2, a0 and a1
    are scratch -- d2 is reloaded from `[0xB3F4]` at 0x0FB3E, and both address
    registers are set again by the routines this returns into.
    """
    a = Asm()
    a.raw("be3c0002").br(0x66, "wide")                # 24x48: a second below
    a.raw("06410018").raw("48aa00030012").br(0x60, "out")
    a.label("wide").raw("be3c0003").br(0x66, "big")   # 48x24: a second right
    a.raw("06400018").raw("48aa00030012").br(0x60, "out")
    a.label("big").raw("be3c").raw(f"{BIG:04x}").br(0x66, "one")
    # Which half of the art the engine gave the first entry decides which side
    # the second one goes. Groups come in pairs, left half then right half of
    # a frame, and the creature animates while it slides, so the first entry
    # lands on either. An even group is a left half and its partner is the
    # group after it, drawn to the right; an odd group is a right half and its
    # partner is the group before it, drawn to the left. Adding one and always
    # going right gets it correct half the time and leaves the other half
    # showing two left halves side by side.
    a.raw("142a000a")                                 # move.b $a(a2), d2
    a.raw("08020000").br(0x66, "rightside")           # btst #0, d2 / bne
    a.raw("06400018").raw("5202").br(0x60, "put")     # left half: partner right
    a.label("rightside")
    a.raw("04400018").raw("5302")                     # right half: partner left
    a.label("put")
    a.raw("48aa00030012")                             # the second entry's place
    a.raw("1542").raw(f"{ENTRY + 0x0A:04x}")          # and its half
    a.br(0x60, "out")
    a.label("one").raw("50ea001c")                    # 24x24: end the list
    a.label("out")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", PLACE_END)


def advance():
    """Every entry the creature has moves with it, not just the first two."""
    a = Asm()
    a.raw("45f8b0b4")                                 # lea $b0b4.w, a2
    a.raw("d552").raw("d76a0002")                     # entry 1
    a.raw("d56a0012").raw("d76a0014")                 # entry 2
    a.raw("0c2e").raw(f"{BIG:04x}").raw("ffff").br(0x66, "out")   # cmpi.b #4,-1(a6)
    a.raw("d56a0024").raw("d76a0026")                 # entry 3
    a.raw("d56a0036").raw("d76a0038")                 # entry 4
    a.label("out")
    return a.done() + b"\x4e\xf9" + struct.pack(">I", ADVANCE_END)


def slots():
    """Two display entries for a figure being slid, four for a 48x48."""
    a = Asm()
    a.raw("102b0002")                                 # move.b $2(a3), d0
    a.raw("4eb9").raw(f"{RECORD:08x}")                # jsr $6f14 -> a1
    a.raw("7002")                                     # moveq #2, d0
    a.raw("0c29").raw(f"{BIG:04x}").raw("0023")       # cmpi.b #4, $23(a1)
    a.br(0x66, "set")
    a.raw("7004")                                     # moveq #4, d0
    a.label("set").raw("31c0").raw(f"{COUNT:04x}")    # move.w d0, $b0b2.w
    return a.done() + b"\x4e\xf9" + struct.pack(">I", SLOTS_END)


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    sites = ((PLACE, PLACE_END, "sprite placement", PLACE_STOCK, place),)
    for at, _end, name, stock, _build in sites:
        if bytes(rom[at:at + len(stock)]) != stock:
            raise SystemExit(f"0x{at:05X} is not the {name}: "
                             f"{bytes(rom[at:at + len(stock)]).hex()}")
    where = {PLACE: (PLACE_NEW, PLACE_NEW_LIMIT),
             SLOTS: (PLACE_NEW + 0x80, PLACE_NEW_LIMIT),
             ADVANCE: (ADVANCE_NEW, ADVANCE_NEW_LIMIT)}
    for at, end, name, _stock, build in sites:
        cursor, limit = where[at]
        code = build()
        if cursor + len(code) > limit:
            raise SystemExit(f"{name} is {len(code)} bytes and 0x{cursor:06X} "
                             f"has {limit - cursor}")
        if any(rom[cursor:cursor + len(code)]):
            raise SystemExit(f"0x{cursor:06X}+{len(code)} is not free: "
                             f"{bytes(rom[cursor:cursor + len(code)]).hex()[:32]}...")
        rom[cursor:cursor + len(code)] = code
        room = end - at
        rom[at:end] = (b"\x4e\xf9" + struct.pack(">I", cursor)
                       + b"\x4e\x71" * ((room - 6) // 2))
        print(f"  0x{at:05X} {name}: jmp 0x{cursor:06X} ({len(code)} bytes), "
              f"rejoins 0x{end:05X}")
    print(f"  a 48x48 creature slides as four sprites, {STEP} pixels apart")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

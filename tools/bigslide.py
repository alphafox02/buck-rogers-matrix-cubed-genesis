"""
Slide a 48x48 creature between squares as four sprites, not one.

A combat figure that is STANDING is plane A tiles. A figure that is MOVING is
hardware sprites: `0x0F9A6` takes it off the board and sets up a display list,
`0x0FA52` blits its cells into VRAM through the chain at `0xB59A` -- which
`bigfigures.py` teaches about 48x48 -- and walks it to the next square. The
sprite side never learned the size, so a 48x48 slid as ONE 24x24 sprite: the
top-left quarter of itself crossing the board. A play session called it "one
box", and it only became visible once `combatgap.py` gave the creature room to
walk at all.

Genesis sprites stop at 4x4 tiles, so 48x48 is four of them. Getting four to
EXIST works and is what this does: `[0xB0B2]` raised to four, all four entries
cleared and prepared at the hide, all four positioned in quadrant order, all
four moved every step. On screen the creature covers its whole footprint while
it slides.

What does not work is giving each of the four a different quarter of the art,
and NOT WIRED INTO THE BUILD is why. Seven attempts, each built and watched
frame by frame:

    positions only, count 2        two entries, both the same quadrant
    count raised at the placement  creature vanishes outright
    count raised at 0x0F9BE        creature vanishes outright
    group into byte $a of entry 2  no change at all
    second entry's side chosen
      from the first's group       no change at all
    four entries, count 4,
      prepared at the hide         all four appear and move -- all the same
                                   quadrant, a 2x2 of one quarter
    byte $a set 0,1,2,3            everything vanishes: $a is not an index
    a record per entry, each with
      its own $1, entries linked
      through $b                   everything vanishes

`0x0C1A4` reads byte `$1` of the figure RECORD an entry points at, times nine,
plus `[0xB1C6]`, as the VRAM tile its blit starts from -- so the quadrant is a
property of the record, not the entry, and four entries sharing one record can
only ever draw one quarter. Replicating the record at `0xB018` into `0xB02A`,
`0xB03C` and `0xB04E` and pointing the entries at the copies is the obvious
answer and makes the creature disappear, so either `$b` is not a plain index
or those addresses are already spoken for. That is where an eighth attempt
should start, with a probe on `0x0C1A4` reading back what d1 actually becomes.

What IS shipped is `bigfigures.py`, which fixes the blit those sprites read
from -- it had no case for size 4 at all -- so a 48x48 slides as one clean
quarter of itself instead of a scramble.

Usage:
    bigslide.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

BIG = 4
ENTRY = 0x12                 # bytes per display entry
STEP = 0x18                  # 24 pixels, one square
LIST = 0xB0B4                # the display entries
COUNT = 0xB0B2               # how many of them the engine reads
RECORD = 0x06F14             # d0 = $2(a3) -> a1 = that creature's record
RECORDS = 0xB018             # the figure records a display entry points into

SETUP = 0x0F9BE
SETUP_END = 0x0F9F4
SETUP_STOCK = bytes.fromhex(
    "31fc0002b0b241f8b0184228000142280003117c000c0002"
    "41f8b0b47011425851c8fffc41f8b0c6117c0001000c117c000200094e75")

PLACE = 0x0FB0E
PLACE_END = 0x0FB36
PLACE_STOCK = bytes.fromhex(
    "be3c0002660c0641001848aa000300126016"
    "be3c0003660c0640001848aa00030012600450ea001c")

ADVANCE = 0x0FB6C
ADVANCE_END = 0x0FB7E
ADVANCE_STOCK = bytes.fromhex("45f8b0b4d552d76a0002d56a0012d76a0014")

# What is left of the 1024 zero bytes at 0x0F1BD8 is not contiguous:
# bigfigures.py ends at 0x0F1EC4 and combatgap.py sits at 0x0F1F00.
# The zero bytes run out at 0x0F1FD8 and are followed by 0xFF padding up to
# the music pointer table at 0x0F2000, so the region takes some of that and
# the free-space check accepts either filler. Eight bytes of margin are left.
BIG_REGION = (0x0F1F20, 0x0F2000)      # setup and placement, 224 bytes
SMALL_REGION = (0x0F1EC4, 0x0F1F00)    # the advance, 60 bytes
FILLER = (0x00, 0xFF)


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

    def back(self, op, label):
        """A short branch to a label already passed."""
        d = self.labels[label] - (len(self.code) + 2)
        if not -128 <= d < 0:
            raise SystemExit(f"{label}: {d} bytes out of short range")
        self.code += bytes((op, d & 0xFF))
        return self

    def dbra(self, reg, label):
        self.code += bytes((0x51, 0xC8 | reg))
        self.code += struct.pack(">h", self.labels[label] - len(self.code))
        return self

    def done(self, rejoin=None):
        for slot, name, pc in self.fix:
            d = self.labels[name] - pc
            if not 0 < d < 128:
                raise SystemExit(f"{name}: {d} bytes out of short range")
            self.code[slot] = d
        out = bytes(self.code)
        return out if rejoin is None else out + b"\x4e\xf9" + struct.pack(">I", rejoin)


def setup():
    """Prepare two display entries, or four for a 48x48, and say which."""
    a = Asm()
    a.raw("102b0002")                                  # move.b $2(a3), d0
    a.raw("4eb9").raw(f"{RECORD:08x}")                 # jsr $6f14 -> a1
    a.raw("0c29").raw(f"{BIG:04x}").raw("0023")        # cmpi.b #4, $23(a1)
    a.raw("57c2")                                      # seq d2  -- $FF if 48x48
    a.raw("7002").raw("9002").raw("9002")              # d0 = 2, or 4
    a.raw("31c0").raw(f"{COUNT:04x}")                  # move.w d0, $b0b2.w

    a.raw("41f8b018")                                  # lea $b018.w, a0  (stock)
    a.raw("42280001").raw("42280003")                  # clr.b $1(a0) / $3(a0)
    a.raw("117c000c0002")                              # move.b #$c, $2(a0)

    # Clear four entries always. The list is scratch and about to be rebuilt,
    # and [0xB0B2] decides how many are read, so the two extra cost nothing
    # and save working the length out.
    a.raw("41f8").raw(f"{LIST:04x}")                   # lea $b0b4.w, a0
    a.raw("70").raw(f"{ENTRY * 4 // 2 - 1:02x}")       # moveq #$23, d0
    a.label("wipe").raw("4258")                        # clr.w (a0)+
    a.dbra(0, "wipe")

    a.raw("41f8").raw(f"{LIST + ENTRY:04x}")           # lea $b0c6.w, a0
    a.raw("117c0001000c")                              # move.b #1, $c(a0)
    a.raw("117c00020009")                              # move.b #2, $9(a0)

    a.raw("4a02").br(0x67, "out")                      # tst.b d2 / beq
    a.raw("43e8").raw(f"{ENTRY:04x}")                  # lea $12(a0), a1
    a.raw("72").raw(f"{ENTRY - 1:02x}")                # moveq #17, d1
    a.label("copy").raw("32d8")                        # move.w (a0)+, (a1)+
    a.dbra(1, "copy")
    # Which quadrant each one draws. It is not in the ENTRY at all: 0x0C1A4
    # takes byte $1 of the figure RECORD the entry points at through $b, times
    # nine, plus [0xB1C6], as the VRAM tile the blit starts from. One record
    # means one quadrant however many entries share it, which is why writing
    # into the entries changed nothing.
    #
    # So the record at 0xB018 is replicated three times -- records are 0x12
    # bytes apart like the entries -- and each copy is given its own slot,
    # with each entry pointed at its own copy.
    a.raw("41f8").raw(f"{RECORDS:04x}")                # lea $b018.w, a0
    a.raw("43e8").raw(f"{ENTRY:04x}")                  # lea $12(a0), a1
    a.raw("72").raw(f"{ENTRY * 3 // 2 - 1:02x}")       # moveq #26, d1
    a.label("rec").raw("32d8")                         # move.w (a0)+, (a1)+
    a.dbra(1, "rec")
    a.raw("7201")                                      # moveq #1, d1
    a.raw("41f8").raw(f"{RECORDS + ENTRY + 0x01:04x}")  # lea $b02b.w, a0
    a.raw("43f8").raw(f"{LIST + ENTRY + 0x0B:04x}")     # lea $b0d1.w, a1
    a.label("link").raw("1081").raw("1281")            # slot, and the link to it
    a.raw("d0fc").raw(f"{ENTRY:04x}").raw("d2fc").raw(f"{ENTRY:04x}")
    a.raw("5201").raw("0c010004")                      # addq / cmpi.b #4, d1
    a.back(0x66, "link")                               # bne
    a.label("out").raw("4e75")
    return a.done()


def place():
    """Where each sprite goes: the stock two cases, and four in quadrant order."""
    a = Asm()
    a.raw("be3c0002").br(0x66, "wide")                 # 24x48: a second below
    a.raw("06410018").raw("48aa00030012").br(0x60, "out")
    a.label("wide").raw("be3c0003").br(0x67, "pair")   # 48x24: a second right
    a.raw("be3c").raw(f"{BIG:04x}").br(0x66, "one")    # 48x48: that and two more
    a.label("pair")
    a.raw("06400018").raw("48aa00030012")              # entry 2: one right
    a.raw("be3c").raw(f"{BIG:04x}").br(0x66, "out")
    a.raw("04400018").raw("06410018")                  # back left, one down
    a.raw("48aa00030024")                              # entry 3
    a.raw("06400018").raw("48aa00030036")              # entry 4: right again
    a.br(0x60, "out")
    a.label("one").raw("50ea001c")                     # 24x24: end the list
    a.label("out")
    return a.done(PLACE_END)


def advance():
    """Every entry the creature has moves with it, not just the first two."""
    a = Asm()
    a.raw("45f8").raw(f"{LIST:04x}")
    a.raw("d552").raw("d76a0002")                      # entry 1
    a.raw("d56a0012").raw("d76a0014")                  # entry 2
    a.raw("0c2e").raw(f"{BIG:04x}").raw("ffff").br(0x66, "out")
    a.raw("d56a0024").raw("d76a0026")                  # entry 3
    a.raw("d56a0036").raw("d76a0038")                  # entry 4
    a.label("out")
    return a.done(ADVANCE_END)


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    sites = ((SETUP, SETUP_END, "display entries", SETUP_STOCK, setup, BIG_REGION),
             (PLACE, PLACE_END, "sprite placement", PLACE_STOCK, place, BIG_REGION),
             (ADVANCE, ADVANCE_END, "sprite advance", ADVANCE_STOCK, advance, SMALL_REGION))
    for at, _e, name, stock, _b, _r in sites:
        if bytes(rom[at:at + len(stock)]) != stock:
            raise SystemExit(f"0x{at:05X} is not the {name}: "
                             f"{bytes(rom[at:at + len(stock)]).hex()}")
    cursor = {}
    for at, end, name, _stock, build, region in sites:
        base, limit = region
        c = cursor.get(region, base)
        c += c & 1
        code = build()
        if c + len(code) > limit:
            raise SystemExit(f"{name} is {len(code)} bytes and 0x{c:06X} has "
                             f"{limit - c}")
        if any(b not in FILLER for b in rom[c:c + len(code)]):
            raise SystemExit(f"0x{c:06X}+{len(code)} is not free: "
                             f"{bytes(rom[c:c + len(code)]).hex()[:32]}...")
        rom[c:c + len(code)] = code
        room = end - at
        rom[at:end] = (b"\x4e\xf9" + struct.pack(">I", c)
                       + b"\x4e\x71" * ((room - 6) // 2))
        print(f"  0x{at:05X} {name}: jmp 0x{c:06X} ({len(code)} bytes), "
              f"rejoins 0x{end:05X}")
        cursor[region] = c + len(code)
    print("  a 48x48 creature slides as four sprites, one per quadrant")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

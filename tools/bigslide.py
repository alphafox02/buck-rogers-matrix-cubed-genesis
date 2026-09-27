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

NOT WIRED INTO THE BUILD, and do not wire it in without reading this.

The three extra entries appear and move correctly -- side by side against the
shipped ROM the creature covers its whole footprint instead of a quarter of it
-- but each entry draws the WRONG QUADRANT. Which group of nine VRAM tiles an
entry shows is assigned by `0x0C0DC` (called from `0x0FB36`) out of the
template copied to `$8(a3)`, and `0x0FABC` fixes up only its first two bytes.
Positioning an entry does not give it art. On screen that is two mismatched
pieces of dinosaur side by side, which is more of the creature and still not
one creature, so it is not an improvement worth shipping.

What is left to do is `0x0C0DC` and the template format at `0xFBF8`: sets are
eight bytes, four words, one offset per facing, and each template is a word
pointer followed by entry bytes to a terminator with bit 7 set. Template
length does NOT track the size class -- class 0 figures use sets of 2, 3 and 4
bytes and class 3 figures use the same spread -- so the entry count is not in
there and the quadrant assignment is what has to be found.

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

ADVANCE = 0x0FB6C
ADVANCE_END = 0x0FB7E
ADVANCE_STOCK = bytes.fromhex("45f8b0b4d552d76a0002d56a0012d76a0014")

NEW = 0x0F1F20               # free: combatgap.py's block ends by 0x0F1F18
NEW_LIMIT = 0x0F1FD0         # music starts at 0x0F2004


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

    def done(self):
        for slot, name, pc in self.fix:
            d = self.labels[name] - pc
            if not 0 < d < 128:
                raise SystemExit(f"{name}: {d} bytes out of short range")
            self.code[slot] = d
        return bytes(self.code)


def place():
    """The stock two cases unchanged, and four entries for a 48x48."""
    a = Asm()
    a.raw("be3c0002").br(0x66, "n2")                  # 24x48
    a.raw("06410018").raw("48aa00030012").br(0x60, "out")
    a.label("n2").raw("be3c0003").br(0x66, "n3")      # 48x24
    a.raw("06400018").raw("48aa00030012").br(0x60, "out")
    a.label("n3").raw("be3c").raw(f"{BIG:04x}").br(0x66, "one")
    a.raw("06400018").raw("48aa00030012")             # entry 2: one square right
    a.raw("04400018").raw("06410018")                 # back left, one square down
    a.raw("48aa00030024")                             # entry 3
    a.raw("06400018").raw("48aa00030036")             # entry 4: right again
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


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    sites = ((PLACE, PLACE_END, "sprite placement", PLACE_STOCK, place),
             (ADVANCE, ADVANCE_END, "sprite advance", ADVANCE_STOCK, advance))
    for at, _end, name, stock, _build in sites:
        if bytes(rom[at:at + len(stock)]) != stock:
            raise SystemExit(f"0x{at:05X} is not the {name}: "
                             f"{bytes(rom[at:at + len(stock)]).hex()}")
    cursor = NEW
    for at, end, name, _stock, build in sites:
        cursor += cursor & 1
        code = build()
        if cursor + len(code) > NEW_LIMIT:
            raise SystemExit("the new blocks do not fit")
        if any(rom[cursor:cursor + len(code)]):
            raise SystemExit(f"0x{cursor:06X}+{len(code)} is not free: "
                             f"{bytes(rom[cursor:cursor + len(code)]).hex()[:32]}...")
        rom[cursor:cursor + len(code)] = code
        room = end - at
        rom[at:end] = (b"\x4e\xf9" + struct.pack(">I", cursor)
                       + b"\x4e\x71" * ((room - 6) // 2))
        print(f"  0x{at:05X} {name}: jmp 0x{cursor:06X} ({len(code)} bytes), "
              f"rejoins 0x{end:05X}")
        cursor += len(code)
    print(f"  a 48x48 creature slides as four sprites, {STEP} pixels apart")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

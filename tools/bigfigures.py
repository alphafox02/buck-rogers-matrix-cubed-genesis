"""
Teach the combat engine a 48x48 creature.

Every combat figure on the board is ONE hardware sprite, three tiles square:

    0C5BC: move.w  #$a00, d4      ; size nibble 0xA = 3 wide, 3 tall
    0C5C4: move.w  d4, (a5)
    0C5D2: mulu.w  #$9, d1        ; nine VRAM tiles per display entry

A bigger creature is therefore not a bigger sprite -- it is several entries.
The size class in the high nibble of the figure record's byte 7 decides how
many and where:

    class 0   1 entry    9 cells   24 x 24   43 figures
    class 2   2 entries 18 cells   24 x 48    1 figure   DESERT APE
    class 3   2 entries 18 cells   48 x 24    8 figures

The cells are blitted into consecutive VRAM tiles through a table of byte
offsets, one per cell, and each group of nine becomes one entry:

    0xB742   00 06 0C 02 08 0E 04 0A 10 | 12 18 1E 14 1A 20 16 1C 22
    0xB754   00 0C 18 02 0E 1A 04 10 1C | 06 12 1E 08 14 20 0A 16 22

Halved those are cell numbers, each group of nine in column-major order --
the order a Genesis sprite reads its tiles. 0xB742's two groups are the top
and bottom halves of a 3x6 frame; 0xB754's are the left and right halves of
a 6x3 one.

Matrix Cubed's `CPIC1.DAX` holds 24x24 (82 sprites) and 48x24 (16), which
land on classes 0 and 3 unchanged, and 48x48 (10) -- the dinosaur among them
-- which has nowhere to go. This adds class 4: four entries, 36 cells, in
quadrant order.

Five sites, each verified against its stock bytes first:

  0xB59A, 0xB606   the two copies of the cell-count-and-table chain, and the
                   only two places in the ROM that name either table.
  0xC268           the slot-width byte. Stock writes 1 for class 0-1 and 2
                   for anything else; `1 << (class >> 1)` is identical for
                   classes 0-3 and gives 4 for class 4.
  0xC2DA           the slot allocator. Nine VRAM tiles per slot from
                   `$B1C6`, `$B1C4` slots available (base 0x33A, 15 slots),
                   so a 48x48 figure needs four of the fifteen. The two
                   stock cases are moved out whole and copied unchanged,
                   because their bounds tests do not agree with each other
                   (`beq` on the count for one slot, `bge` on count-1 for
                   two) and making them agree would change which encounters
                   the engine accepts.
  0xC358           the first entry's position: stock lifts it 24px for
                   class 2, and class 4 needs the same lift.
  0xC30E           the tail that builds the second entry. Class 4 gets a
                   third and fourth, below the first two.

Horizontal flip is carried in bit 7 of `d5` and the stock wide class answers
it by swapping which group each entry draws, so a mirrored creature still
reads left to right. The new class does the same for its lower two.

The new code and table go in the 1024 zero bytes at 0x0F1BD8, below where
inject_music starts writing at 0x0F2000.

Usage:
    bigfigures.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

NEW_CODE = 0x0F1BD8          # 1024 zero bytes; music starts at 0x0F2000
NEW_CODE_LIMIT = 0x0F1F00

TABLE_A = 0xB742             # 3x6, top group then bottom
TABLE_B = 0xB754             # 6x3, left group then right
BAIL = 0x0C3AC               # "no room" exit inside the placement routine
RESUME = 0x0C2FE             # where the allocator falls through to
ENTRY2 = 0x0C32A             # builds the second display entry
WRITE_ENTRY = 0x0C36A        # the shared tail that writes one entry, then rts

CLASS_BIG = 4
BIG_CELLS = 36               # four groups of nine
BIG_SLOTS = 4

CHAIN_SITES = (0xB59A, 0xB606)
CHAIN_LEN = 0x28
CHAIN_STOCK = bytes.fromhex(
    "b03c0002660a7e122c3c0000b7426018"
    "b03c0003660a7e122c3c0000b75460087e092c3c0000b742")

SLOTW = 0xC268
SLOTW_LEN = 0x10
SLOTW_STOCK = bytes.fromhex("122efffab23c00016204720160027202")

ALLOC = 0xC2DA
ALLOC_LEN = 0x24
ALLOC_STOCK = bytes.fromhex(
    "b83c0001620ebc78b1c4670000c65278b0b2"
    "601030065340b078b1c46c0000b45478b0b2")

TAIL = 0xC30E
TAIL_LEN = 0x10
TAIL_STOCK = bytes.fromhex("b83c0001630a5246d6fc00126100000e")

LIFT = 0xC358
LIFT_LEN = 0x0A
LIFT_STOCK = bytes.fromhex("b83c0002660404430018")


class Asm:
    """Straight-line 68000 with short forward branches. No cleverness."""

    def __init__(self, at):
        self.at = at
        self.code = bytearray()
        self.labels = {}
        self.fix = []

    def raw(self, hexes):
        self.code += bytes.fromhex(hexes.replace(" ", ""))
        return self

    def imm(self, hexes, value):
        self.raw(hexes)
        self.code += struct.pack(">H", value)
        return self

    def br(self, op, label):
        self.fix.append((len(self.code) + 1, label, len(self.code) + 2))
        self.code += bytes((op, 0))
        return self

    def jsr(self, target):
        self.code += b"\x4e\xb9" + struct.pack(">I", target)
        return self

    def jmp(self, target):
        self.code += b"\x4e\xf9" + struct.pack(">I", target)
        return self

    def label(self, name):
        self.labels[name] = len(self.code)
        return self

    def done(self):
        for slot, name, pc in self.fix:
            disp = self.labels[name] - pc
            if not 0 < disp < 128:
                raise SystemExit(f"{name}: {disp} bytes, out of short range")
            self.code[slot] = disp
        return bytes(self.code)


def layout_48x48() -> bytes:
    """
    Four groups of nine, quadrant by quadrant: top-left, top-right,
    bottom-left, bottom-right, each nine in column-major order. Which is to
    say 0xB754 for the top half and 0xB754 again, shifted a row of cells
    down, for the bottom.
    """
    out = bytearray()
    for base_row in (0, 3):
        for base_col in (0, 3):
            for col in range(3):
                for row in range(3):
                    cell = (base_row + row) * 6 + base_col + col
                    out.append(cell * 2)
    assert len(out) == BIG_CELLS
    return bytes(out)


def chain(new_table: int) -> bytes:
    """
        moveq   #9, d7              ; 9 cells, table A
        move.l  #TABLE_A, d6
        subq.b  #2, d0
        bmi.b   done                ; class 0, 1 -> 24 x 24
        moveq   #$12, d7            ; 18 cells for classes 2 and 3
        subq.b  #1, d0
        bmi.b   done                ; class 2 -> 24 x 48, table A
        bne.b   big                 ; class 4 -> below
        move.l  #TABLE_B, d6        ; class 3 -> 48 x 24
        bra.b   done
    big:
        moveq   #$24, d7            ; 36 cells
        move.l  #NEW, d6            ; -> 48 x 48
    done:

    Order matters: `moveq` sets N and Z, so every test reads the `subq`
    immediately before it rather than across one.
    """
    a = Asm(0)
    a.raw("7e09")
    a.raw("2c3c"); a.code += struct.pack(">I", TABLE_A)
    a.raw("5500").br(0x6B, "done")
    a.raw("7e12")
    a.raw("5300").br(0x6B, "done").br(0x66, "big")
    a.raw("2c3c"); a.code += struct.pack(">I", TABLE_B)
    a.br(0x60, "done")
    a.label("big").raw("7e24")
    a.raw("2c3c"); a.code += struct.pack(">I", new_table)
    a.label("done")
    out = a.done()
    if len(out) > CHAIN_LEN:
        raise SystemExit("the class chain does not fit")
    return out + b"\x4e\x71" * ((CHAIN_LEN - len(out)) // 2)


def slot_width() -> bytes:
    """d1 = 1 << (class >> 1): 1, 1, 2, 2 for classes 0-3 -- what the stock
    chain produced -- and 4 for class 4. d0 is dead here, reloaded at
    0xC28C before its next use."""
    out = bytes.fromhex("122efffa" "e209" "7001" "e328" "1200")
    return out + b"\x4e\x71" * ((SLOTW_LEN - len(out)) // 2)


def allocator(at) -> bytes:
    """Four slots for class 4; the two stock cases unchanged, inverted only
    so the "no room" exit can be a `jmp` (0xC3AC is far out of branch range
    from here)."""
    a = Asm(at)
    a.imm("b83c", CLASS_BIG).br(0x66, "stock")
    a.raw("3006").raw("5640").raw("b078b1c4").br(0x6D, "ok4").jmp(BAIL)
    a.label("ok4").raw("5878b0b2").jmp(RESUME)
    a.label("stock")
    a.raw("b83c0001").br(0x62, "two")
    a.raw("bc78b1c4").br(0x66, "ok1").jmp(BAIL)
    a.label("ok1").raw("5278b0b2").jmp(RESUME)
    a.label("two").raw("3006").raw("5340").raw("b078b1c4").br(0x6D, "ok2").jmp(BAIL)
    a.label("ok2").raw("5478b0b2").jmp(RESUME)
    return a.done()


def lift(at) -> bytes:
    """Stock lifts the first entry 24px for class 2. Class 4's top row needs
    the same lift; its bottom row goes back down in `tail`."""
    a = Asm(at)
    a.raw("b83c0002").br(0x67, "shift")
    a.imm("b83c", CLASS_BIG).br(0x66, "out")
    a.label("shift").raw("04430018")
    a.label("out").raw("4e75")
    return a.done()


def tail(at) -> bytes:
    """
    Stock builds a second entry for any class above 1. Class 4 gets a third
    and fourth under the first two.

    On entry d2 is x, d3 is y, d5 carries the flip bits, d6 is the slot and
    a3 the display record. After 0xC32A they are one entry further on and
    d2 has moved right 24. The lower row goes back to x, down 24, and takes
    the remaining two groups -- swapped when the figure is mirrored, the
    same way 0xC32A swaps the upper two.
    """
    a = Asm(at)
    a.raw("b83c0001").br(0x63, "out")          # class 0, 1 -> one entry only
    a.raw("5246")                              # addq.w  #1, d6
    a.raw("d6fc0012")                          # adda.w  #$12, a3
    a.jsr(ENTRY2)                              # the stock second entry
    a.imm("b83c", CLASS_BIG).br(0x66, "out")   # everything else is done

    a.raw("04420018")                          # subi.w  #$18, d2   x back
    a.raw("06430018")                          # addi.w  #$18, d3   y back down
    a.raw("5246").raw("d6fc0012")              # next slot, next record
    a.raw("4a05").br(0x6A, "plain")            # tst.b d5 -> flipped?
    a.raw("5405").raw("1745000a")              # flipped: group 3 on the left
    a.raw("5305").br(0x60, "four")             #          group 2 on the right
    a.label("plain")
    a.raw("5205").raw("1745000a")              # group 2 on the left
    a.raw("5205")                              # group 3 on the right
    a.label("four")
    a.jsr(WRITE_ENTRY)                         # write the third entry
    a.raw("06420018")                          # addi.w  #$18, d2   right 24
    a.raw("5246").raw("d6fc0012")
    a.raw("1745000a")                          # whichever group d5 now holds
    a.jsr(WRITE_ENTRY)                         # write the fourth
    a.label("out").raw("4e75")
    return a.done()


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)

    checks = ((CHAIN_SITES[0], "class chain A", CHAIN_STOCK),
              (CHAIN_SITES[1], "class chain B", CHAIN_STOCK),
              (SLOTW, "slot-width byte", SLOTW_STOCK),
              (ALLOC, "slot allocator", ALLOC_STOCK),
              (TAIL, "second-entry tail", TAIL_STOCK),
              (LIFT, "first-entry lift", LIFT_STOCK))
    for at, name, stock in checks:
        if bytes(rom[at:at + len(stock)]) != stock:
            raise SystemExit(f"0x{at:05X} is not the {name}: "
                             f"{bytes(rom[at:at + len(stock)]).hex()}")

    for rec in range(0x9A14, len(rom), 8):
        if rom[rec + 4] & 0x80:
            break
        if rom[rec + 7] >> 4 >= CLASS_BIG:
            raise SystemExit(f"figure 0x{rom[rec + 4]:02X} already has class "
                             f"{rom[rec + 7] >> 4}")

    cursor = NEW_CODE
    table, cursor = cursor, cursor + BIG_CELLS
    rom[table:cursor] = layout_48x48()

    blocks = []
    for name, build in (("allocator", allocator), ("lift", lift), ("tail", tail)):
        cursor += cursor & 1
        code = build(cursor)
        rom[cursor:cursor + len(code)] = code
        blocks.append((name, cursor, len(code)))
        cursor += len(code)
    if cursor > NEW_CODE_LIMIT:
        raise SystemExit("the new code runs past its region")
    alloc_at, lift_at, tail_at = (a for _, a, _ in blocks)

    print(f"  0x{table:06X} class {CLASS_BIG} layout: {BIG_CELLS} cells in "
          f"four groups of nine = 48x48 px")
    for name, at, size in blocks:
        print(f"  0x{at:06X} {name}, {size} bytes")

    for at in CHAIN_SITES:
        rom[at:at + CHAIN_LEN] = chain(table)
        print(f"  0x{at:05X} cell count and layout table know class {CLASS_BIG}")

    rom[SLOTW:SLOTW + SLOTW_LEN] = slot_width()
    print(f"  0x{SLOTW:05X} slot width = 1 << (class >> 1) "
          f"({BIG_SLOTS} of the 15 combat slots for class {CLASS_BIG})")

    def trampoline(at, length, target, op=b"\x4e\xf9"):
        rom[at:at + length] = (op + struct.pack(">I", target)
                               + b"\x4e\x71" * ((length - 6) // 2))

    trampoline(ALLOC, ALLOC_LEN, alloc_at)
    print(f"  0x{ALLOC:05X} jmp 0x{alloc_at:06X}  (slot allocator)")
    trampoline(LIFT, LIFT_LEN, lift_at, op=b"\x4e\xb9")
    print(f"  0x{LIFT:05X} jsr 0x{lift_at:06X}  (first entry lifted for "
          f"classes 2 and {CLASS_BIG})")
    trampoline(TAIL, TAIL_LEN, tail_at, op=b"\x4e\xb9")
    print(f"  0x{TAIL:05X} jsr 0x{tail_at:06X}  (class {CLASS_BIG} gets a "
          f"third and fourth entry)")

    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

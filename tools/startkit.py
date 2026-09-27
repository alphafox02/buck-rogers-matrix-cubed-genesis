# SPDX-License-Identifier: MIT
"""
Hand the starting party gear it can fight with.

`TREASURE` at `0x0392C` reads its arguments off the script stream through
`0x404A` -- money into `[0xBA34]`, a count into `[0xB9F3]`, then that many item
ids, each dropped if it is above 0x5D or in the 34-byte exclusion list at
`0x03978`. What survives lands in the party's item pool at `0xB9F4`.

The kit is one line, and it appears in three blocks -- 0x00, 0x10 and 0x13 --
at the same encoding, one `mode value` pair per argument:

    29 1c 27  02 40 1f  00 14  00 16 00 16 00 16 00 16  00 17 00 17 ...
              TREASURE  8000   20    four battle armor   two w/fields

Read live out of `0xB9F4` after the opening, what the party actually holds is
four battle armor, two battle armor with fields and two healing grenades.
**No weapons at all.** The item table decodes cleanly -- 10-byte records at
`0x0F17D8`, names composed from the word list at `0x11DC4`, `knife` at 1 to
`lunarian heavy body armor` at 90 -- so the ids are known and the line is a
straight data edit.

This replaces the twenty ids with the best of each kind that TREASURE will
actually pass:

    6 x mercurian battle armor   0x57   the heaviest armour in the table
    6 x lunarian laser rifle     0x48   the heaviest gun it will accept
    2 x lunarian sonic stunner   0x4A
    2 x mercurian heat gun       0x43
    4 x grenade, treating wounds 0x21   healing, and already in the stock kit

None of them is in the exclusion list and none is above 0x5D, so all twenty
arrive. The count and the encoding are untouched -- only the id bytes change.

Usage:
    startkit.py <in.gen> <out.gen>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import expand
import genesis_ecl
import integrity

# The stock kit, in the order the pairs appear in the script.
STOCK = [0x16, 0x16, 0x16, 0x16, 0x17, 0x17, 0x21, 0x21, 0x21, 0x08, 0x08,
         0x0F, 0x06, 0x06, 0x06, 0x12, 0x0A, 0x0A, 0x23, 0x23]

# Each id replaced by the best of ITS OWN KIND, so the kit keeps every piece
# of equipment it had. Nothing is dropped and nothing is doubled up: a laser
# pistol becomes a better laser, the rocket rifle a better rocket, the armour
# better armour. The one substitution that is not an upgrade is the grenade
# launcher, and only because TREASURE throws 0x0F away -- it is in the
# exclusion list at 0x03978, so the stock kit never delivered it either. A
# rocket launcher stands in, which is the same shape of weapon and does arrive.
UPGRADE = {
    0x16: (0x57, "battle armor",     "mercurian battle armor"),
    0x17: (0x17, "battle armor w/fields", "battle armor w/fields (no better exists)"),
    0x21: (0x21, "grenade, treating wounds", "grenade, treating wounds (kept)"),
    0x08: (0x48, "laser pistol",     "lunarian laser"),
    0x0F: (0x11, "grenade launcher", "rocket launcher (0x0F is dropped by TREASURE)"),
    0x06: (0x46, "bolt gun",         "lunarian bolt gun"),
    0x12: (0x3E, "polearm",          "mercurian polearm"),
    0x0A: (0x2D, "rocket rifle",     "martian rocket"),
    0x23: (0x23, "grenade, dazzle",  "grenade, dazzle (kept)"),
}
KIT = [UPGRADE[i][0] for i in STOCK]

# TREASURE drops an id above 0x5D or anywhere in this list, so every
# replacement is checked against it before the build goes anywhere.
EXCLUDED = bytes.fromhex(
    "0102043107 0b0c0d0f13 1c1d1e2022 27292c2f30 3233343 83a"
    "3d3f42404547494b35".replace(" ", ""))


def find(code):
    """Offset of the first id byte of the kit, or None."""
    for i in range(len(code) - 2 * len(STOCK)):
        if all(code[i + 2 * n] == 0 and code[i + 2 * n + 1] == STOCK[n]
               for n in range(len(STOCK))):
            return i
    return None


def apply(rom: bytes) -> bytes:
    assert len(KIT) == len(STOCK), "the count byte must not change"
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    geo = expand.read_geo_stream(rom)
    touched = 0
    for n, (bid, code, text) in enumerate(blocks):
        at = find(code)
        if at is None:
            continue
        out = bytearray(code)
        for k, item in enumerate(KIT):
            out[at + 2 * k + 1] = item
        blocks[n] = (bid, bytes(out), text)
        touched += 1
        print(f"  area 0x{bid:02X}: starting kit rewritten at 0x{at:04X}")
    if not touched:
        raise SystemExit("the starting kit is not where this expects it")
    from collections import Counter
    for old_id in sorted(Counter(STOCK), key=STOCK.index):
        new_id, was, now = UPGRADE[old_id]
        print(f"    {STOCK.count(old_id)} x {was} (0x{old_id:02X}) -> {now} "
              f"(0x{new_id:02X})")

    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(geo)
    return builder.finish()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes())
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

"""
Give ADDNPC a bigger table, so Matrix Cubed's own NPCs can join.

`ADDNPC` looks its id up in a table of `(npc id, roster record id)` pairs at
`0x048DA`, reached by `lea.l $48da.l, a0` whose operand is at `0x048BA`. The
table is seven pairs long and ends at `0x048E8`, which is the roster loader's
first instruction -- there is nowhere to append, and the scan that reads it
has no terminator, so a miss walks into that code (see docs/re_notes.md).

The id in the table IS a roster record id -- see npcmap.py. So the table is
only a list of which roster records are allowed to join a party, and a
character who is in the roster but not in the table cannot be named.

That is exactly Killer Kane's position: `add_creatures.py` already puts him
in the roster at `0x42` with 90 hit points and his own figure, and the seven
entries are all Countdown's. Folding him onto one of them was tried first and
sent him to ZANE, a bit-player with **4 hit points**, which a play session
spotted as "a baby on my team". So this relocates the table into free space
at the end of the cartridge and adds his id.

Relocating is safe in a way appending is not: the operand moves with the
table, and the original seven pairs are copied verbatim, so every id
Countdown's own scripts use resolves exactly as before.

Usage:
    npctable.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integrity
import npcmap

LEA_OPERAND = 0x048BA       # operand of `lea.l $48da.l, a0`
TABLE = 0x048DA             # the stock table
TABLE_END = 0x048E8         # where the loader's code starts
# The last 1.9 KB of the cartridge, past the title art at 0x1FA000-0x1FF883.
# Nothing else is written here and the 0x0FFFB0 integrity sum only covers the
# first megabyte.
FREE = 0x1FFF00


def patch(rom: bytes):
    out = bytearray(rom)
    stock = bytes(rom[TABLE:TABLE_END])
    if len(stock) % 2:
        raise SystemExit("the stock ADDNPC table is not a whole number of pairs")
    pairs = [(stock[i], stock[i + 1]) for i in range(0, len(stock), 2)]
    have = {npc for npc, _ in pairs}

    added = []
    for npc, rec in sorted(npcmap.ADDED.items()):
        if npc in have:
            continue
        pairs.append((npc, rec))
        added.append((npc, rec))

    blob = b"".join(bytes(p) for p in pairs)
    out[FREE:FREE + len(blob)] = blob
    struct.pack_into(">I", out, LEA_OPERAND, FREE)

    print(f"  ADDNPC table: {len(stock) // 2} stock pairs + {len(added)} added"
          f" -> 0x{FREE:06X}+{len(blob)}, lea at 0x{LEA_OPERAND:05X}")
    for npc, rec in added:
        print(f"    0x{npc:02X} {npcmap.GENESIS.get(npc, '?')} may now join")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = integrity.repair(patch(src.read_bytes()))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

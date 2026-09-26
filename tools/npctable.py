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
import genesis_ecl
import integrity
import lzw_encode
import npcmap

STREAM_OPERAND = 0x048F2    # the lea that names the roster stream
NEW_STREAM = 0x1B1000
RECORD = 214
JOINABLE = 0x52             # 1 on a character who may join a party

LEA_OPERAND = 0x048BA       # operand of `lea.l $48da.l, a0`
TABLE = 0x048DA             # the stock table
TABLE_END = 0x048E8         # where the loader's code starts
# The last 1.9 KB of the cartridge, past the title art at 0x1FA000-0x1FF883.
# Nothing else is written here and the 0x0FFFB0 integrity sum only covers the
# first megabyte.
FREE = 0x1FFF00


def joinable(rom: bytearray):
    """Mark the ids this adds as characters rather than monsters.

    Byte 0x52 of a roster record separates the two. All seven of Countdown's
    own joinable NPCs carry 1 there and only seven of the other 83 records
    do, so it is the flag that says a record may stand on the party's side.

    Killer Kane comes in through `add_creatures.py`, which writes creatures,
    so his reads 0. A play session found what that means: "why is killer kane
    in the fight but appears to be on the bad guys side... buck and him are
    fighting against one another." In DOS he is on the roster -- the capture
    of the original shows LEANDER, KILLER KANE and BUCK ROGERS together under
    NAME/AC/HP -- so an ally is what he is supposed to be.
    """
    at = struct.unpack_from(">I", rom, STREAM_OPERAND)[0]
    blob = bytearray(genesis_ecl.decompress(rom[at:at + 0x20000], limit=0x20000))
    count = struct.unpack_from(">H", blob, 0)[0]
    base = 2 + count
    ids = list(blob[2:base])
    fixed = []
    for rid in sorted(npcmap.ADDED):
        if rid not in ids:
            continue
        off = base + ids.index(rid) * RECORD + JOINABLE
        if blob[off] == 1:
            continue
        blob[off] = 1
        fixed.append(rid)
    if not fixed:
        return
    packed = lzw_encode.compress(bytes(blob))
    if bytes(genesis_ecl.decompress(packed, limit=0x20000)) != bytes(blob):
        raise SystemExit("repacked roster does not decompress to itself")
    rom[NEW_STREAM:NEW_STREAM + len(packed)] = packed
    struct.pack_into(">I", rom, STREAM_OPERAND, NEW_STREAM)
    for rid in fixed:
        print(f"    0x{rid:02X} {npcmap.GENESIS.get(rid, '?')} marked joinable"
              f" (record byte 0x{JOINABLE:02X})")
    print(f"  roster restream {len(packed)} bytes at 0x{NEW_STREAM:06X}"
          f" (was 0x{at:06X})")


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
    joinable(out)
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = integrity.repair(patch(src.read_bytes()))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

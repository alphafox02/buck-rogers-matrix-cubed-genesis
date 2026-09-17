"""
Make the combat figure directory additive.

A monster's artwork is found by its own id: the figure directory at 0x9A14
holds 8-byte records {pointer, id, chunk, flags} and the ids run 0x00-0x3E,
matching the monster stream's ids entry for entry over the first 51. So a
creature added to the roster with no figure of the same id falls through to
whatever the miss path substitutes.

The directory is 52 records and cannot grow in place, but it moves the same
way the picture ones did. Six operands load its base:

    0359A  lea.l $9a14.l, a0
    099C6  lea.l $9a14.l, a1      the search itself
    099F6  lea.l $9a14.l, a1      the miss fallback softfail.py writes
    0C3D2  lea.l $9a14.l, a0
    0CB48  lea.l $9a14.l, a0
    0FBAE  lea.l $9a14.l, a0

All six are retargeted together. The terminator is a record whose id byte
has bit 7 set, which is what the search tests with `bmi`.

Longword alignment matters here for the same reason it did for the pictures:
`movea.l (a1), a0` on an odd address is a 68000 address error, which is a
hard freeze rather than a glitch.

Usage:
    expand_figures.py <in.gen> <out.gen> <id>:<source_id> ...

Each new id copies the record of an existing one, so it inherits real
artwork rather than a placeholder. Injecting its own art is separate work;
this only makes the slot exist.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

DIRECTORY = 0x09A14
RECORD = 8
OPERANDS = (0x0359C, 0x099C8, 0x099FA, 0x0C3D4, 0x0CB4A, 0x0FBB0)
NEW_DIRECTORY = 0x1B1800        # clear of the pictures and the monster stream


def read(rom, at):
    recs = []
    while rom[at + 4] < 0x80 and len(recs) < 200:
        recs.append(bytes(rom[at:at + RECORD]))
        at += RECORD
    return recs, bytes(rom[at:at + RECORD])


def apply(rom: bytes, additions) -> bytes:
    rom = bytearray(rom)
    base = struct.unpack_from(">I", rom, OPERANDS[0])[0]
    recs, term = read(rom, base)
    have = {r[4]: r for r in recs}
    print(f"  figure directory holds {len(recs)}, ids "
          f"0x{min(have):02X}-0x{max(have):02X}")

    added = []
    for new_id, src_id in additions:
        if new_id in have:
            continue
        if src_id not in have:
            sys.exit(f"no figure 0x{src_id:02X} to copy for 0x{new_id:02X}")
        rec = bytearray(have[src_id])
        rec[4] = new_id
        recs.append(bytes(rec))
        have[new_id] = bytes(rec)
        added.append((new_id, src_id))
    if not added:
        print("  nothing to add")
        return bytes(rom)

    at = (NEW_DIRECTORY + 3) & ~3
    for r in recs:
        rom[at:at + RECORD] = r
        at += RECORD
    rom[at:at + RECORD] = term
    for site in OPERANDS:
        struct.pack_into(">I", rom, site, (NEW_DIRECTORY + 3) & ~3)
    print(f"  added {len(added)}: "
          + ", ".join(f"0x{n:02X}<-0x{s:02X}" for n, s in added[:8])
          + (" ..." if len(added) > 8 else ""))
    print(f"  {len(recs)} records at 0x{(NEW_DIRECTORY + 3) & ~3:06X}; "
          f"{len(OPERANDS)} operands retargeted")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    adds = []
    for spec in sys.argv[3:]:
        a, b = spec.split(":")
        adds.append((int(a, 0), int(b, 0)))
    out = apply(src.read_bytes(), adds)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

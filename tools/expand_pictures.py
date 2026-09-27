# SPDX-License-Identifier: MIT
"""
Make the ECL picture directory additive.

Countdown's directory holds 57 pictures, ids 0x20-0x6F. Matrix Cubed names
31, and 15 of those ids are not in it -- 0x02, 0x1D-0x1F, 0x37-0x39, 0x60,
0x62, 0x65-0x68, 0x6A, 0x6B. The id list at 0x51326 is followed one byte
later by the pointer array at 0x51360, so it cannot grow in place.

It can be relocated, which is the same move that made the ECL and GEO
directories additive. Three tables move together:

    0x51326  ids, one byte each, negative-terminated
    0x51360  32-bit pointers to the picture data
    0x51444  32-bit pointers to animation metadata

and five instruction operands are retargeted:

    0x0B7C2  lea ids      (the PICTURE loader at 0x0B7B4)
    0x0B7C8  lea pointers
    0x0B7CE  lea metadata
    0x01B36  lea ids      (a second consumer that looks up id 0x6F)
    0x01B3C  lea pointers

Metadata is a count byte followed by that many entries; a count of zero
means the picture does not animate. New entries point at an existing
zero-count blob rather than inventing a format that has not been reversed.

Usage:
    expand_pictures.py <in.gen> <out.gen> <id> ...
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

def _align(at):
    """
    Longword tables must start on an even address.

    `at += len(ids) + 2` after the id list puts the pointer tables wherever
    the id count happens to leave them, and an odd count leaves them odd.
    The 68000 raises an address error on a longword read from an odd
    address, so `movea.l (a1), a0` in the loader froze the machine the
    moment a picture was looked up -- which is every picture. 57 stock ids
    landed odd and so did 65.
    """
    return (at + 3) & ~3


# The ECL picture directory: ids, data pointers, animation metadata.
IDS, PTRS, META = 0x51326, 0x51360, 0x51444
OPERANDS = ((0x0B7C2, "ids"), (0x0B7C8, "ptrs"), (0x0B7CE, "meta"),
            (0x01B36, "ids"), (0x01B3C, "ptrs"))

# The VIEW big-picture directory. Two tables, two operands, no metadata.
BIG_IDS, BIG_PTRS = 0x51302, 0x5130A
BIG_OPERANDS = ((0x0B768, "ids"), (0x0B76E, "ptrs"))

# A metadata record that really does hold still.
#
# Reusing an existing zero-count record was wrong. The count byte being zero
# does not mean "no animation" -- the loader at 0x0B810 then takes `record+1`
# as a single animation STREAM, and the stream is pairs of (frame, duration)
# ending in a negative byte that jumps back to the start:
#
#     id 0x20: 00 | 00 08 01 01 02 01 03 01 04 02 05 01 01 01 | f1 00
#              ^count  seven (frame, duration) pairs            ^-15, loops
#
# So every injected picture inherited id 0x20's six-frame cycle while having
# exactly one frame, and stepped through five frames that do not exist. That
# is the scrambled, moving portrait.
#
# This record is one pair that loops to itself: frame 0, held, for ever.
STILL_AT = 0x1B0900
STILL = bytes((0x00,        # count
               0x00, 0x7F,  # frame 0, long duration
               0xFD,        # -3: back to the same pair
               0x00))

NEW_TABLES = 0x1B0000        # tables here, artwork from 0x1C0000 up
BIG_TABLES = 0x1B0800


def read(rom, ids_at=IDS, ptrs_at=PTRS, meta_at=META):
    ids, a = [], ids_at
    while rom[a] < 0x80:
        ids.append(rom[a])
        a += 1
    n = len(ids)
    ptrs = [struct.unpack_from(">I", rom, ptrs_at + k * 4)[0] for k in range(n)]
    meta = ([struct.unpack_from(">I", rom, meta_at + k * 4)[0] for k in range(n)]
            if meta_at else None)
    return ids, ptrs, meta


def write_still(rom):
    """Put the never-animates record in the ROM and return its address."""
    rom[STILL_AT:STILL_AT + len(STILL)] = STILL
    return STILL_AT


def apply_big(rom: bytes, new_ids) -> bytes:
    """Same move for the VIEW directory, which has no metadata table."""
    rom = bytearray(rom)
    ids, ptrs, _ = read(bytes(rom), BIG_IDS, BIG_PTRS, None)
    print(f"  big-picture directory holds {len(ids)}: {[hex(x) for x in ids]}")
    added = [p for p in new_ids if p not in ids]
    if not added:
        print("  nothing to add")
        return bytes(rom)
    for pid in added:
        ids.append(pid)
        ptrs.append(ptrs[0])
    print(f"  adding {[hex(x) for x in added]} -> {len(ids)} total")
    at = BIG_TABLES
    id_at = at
    rom[at:at + len(ids)] = bytes(ids)
    rom[at + len(ids)] = 0xFF
    at = _align(at + len(ids) + 1)
    ptr_at = at
    for p in ptrs:
        struct.pack_into(">I", rom, at, p)
        at += 4
    where = {"ids": id_at, "ptrs": ptr_at}
    for site, kind in BIG_OPERANDS:
        struct.pack_into(">I", rom, site, where[kind])
        print(f"    0x{site:05X} -> 0x{where[kind]:06X} ({kind})")
    return integrity.repair(bytes(rom))


def apply(rom: bytes, new_ids) -> bytes:
    """
    Add ids to the directory.

    Every id added MUST have artwork injected in the same build. An added id
    with no art of its own inherits `ptrs[0]`, which is id 0x20 -- the
    largest picture in the ROM, six frames and 12 KB. That is what made the
    first attempt at this crash: an id the directory lacked used to take the
    engine's own fallback at 0x082EC, which picks something sensible and
    retries, and adding the id turned every one of those safe misses into a
    hit on the biggest blob in the cartridge. The caller is responsible for
    following this with the matching injection.
    """
    rom = bytearray(rom)
    ids, ptrs, meta = read(bytes(rom))
    print(f"  directory holds {len(ids)} pictures, ids "
          f"0x{min(ids):02X}-0x{max(ids):02X}")
    blank = ptrs[0]
    still = write_still(rom)
    added = []
    for pid in new_ids:
        if pid in ids:
            continue
        ids.append(pid)
        ptrs.append(blank)          # placeholder until art is injected
        meta.append(still)
        added.append(pid)
    if not added:
        print("  nothing to add")
        return bytes(rom)
    print(f"  adding {len(added)}: {[hex(x) for x in added]} -> {len(ids)} total")

    at = NEW_TABLES
    id_at = at
    rom[at:at + len(ids)] = bytes(ids)
    rom[at + len(ids)] = 0xFF
    at = _align(at + len(ids) + 1)
    ptr_at = at
    for p in ptrs:
        struct.pack_into(">I", rom, at, p)
        at += 4
    meta_at = at
    for m in meta:
        struct.pack_into(">I", rom, at, m)
        at += 4

    where = {"ids": id_at, "ptrs": ptr_at, "meta": meta_at}
    for site, kind in OPERANDS:
        struct.pack_into(">I", rom, site, where[kind])
        print(f"    0x{site:05X} -> 0x{where[kind]:06X} ({kind})")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    args = [a for a in sys.argv[3:] if a != "--bigpic"]
    new = [int(v, 0) for v in args]
    fn = apply_big if "--bigpic" in sys.argv else apply
    out = fn(src.read_bytes(), new)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

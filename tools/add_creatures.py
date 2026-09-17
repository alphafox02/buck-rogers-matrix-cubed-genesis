"""
Give Matrix Cubed's own creatures slots in the roster.

Countdown ships 54 monsters; Matrix Cubed has 36 it never had. They were
substituted by role -- a leader for a leader, a robot for a robot -- which
keeps a fight the right shape but shows the player the substitute's name.

The 214-byte record layout has not been reversed and does not need to be. A
new slot CLONES the record of the creature it used to stand in for, so it is
a valid record by construction and carries stats that suit the role, and
then takes Matrix Cubed's name. The name is the first sixteen bytes, read
for display and indexed by nothing.

Monster id and figure id are the same number -- the two id lists match entry
for entry over the first 51 -- so every new slot also needs a figure record
at the same id, cloning the same source. tools/expand_figures.py does that;
this tool checks it has been done and refuses otherwise, because a monster
with no figure falls through the miss path.

The stream is compressed. It is decompressed, extended, repacked, and the
repack is verified by decompressing it again before it goes in.

Usage:
    add_creatures.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import expand_figures
import genesis_ecl
import integrity
import lzw_encode
import monstermap

STREAM_OPERAND = 0x048F2
RECORD = 214
NAME = 16

# The enlarged stream is written somewhere new, not over the old one.
#
# Stock packs into 2809 bytes at 0x09E77C and the bytes after it are real
# data, not padding. Adding 36 creatures takes the pack to about 4 KB, so
# writing it back in place overran roughly 1290 bytes of whatever followed.
# The stream is reached from one lea, so it relocates the same way the
# picture and figure directories do.
#
# 0x1B1000 is below the figure directory at 0x1B4000, with room for the
# stream to grow into.
NEW_STREAM = 0x1B1000


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    at = struct.unpack_from(">I", rom, STREAM_OPERAND)[0]
    blob = bytearray(genesis_ecl.decompress(rom[at:at + 0x20000], limit=0x20000))
    count = struct.unpack_from(">H", blob, 0)[0]
    base = 2 + count
    ids = list(blob[2:base])
    recs = [bytes(blob[base + k * RECORD:base + (k + 1) * RECORD])
            for k in range(count)]
    have = dict(zip(ids, recs))

    figs, _ = expand_figures.read(
        rom, struct.unpack_from(">I", rom, expand_figures.OPERANDS[0])[0])
    fig_ids = {r[4] for r in figs}

    added = 0
    for nid, (name, src) in sorted(monstermap.NEW_CREATURES.items()):
        if nid in have:
            continue
        if src not in have:
            sys.exit(f"no monster 0x{src:02X} to clone for {name}")
        if nid not in fig_ids:
            sys.exit(f"0x{nid:02X} {name}: no figure record -- "
                     f"run expand_figures first")
        rec = bytearray(have[src])
        rec[:NAME] = name.encode("ascii", "replace")[:NAME - 1].ljust(NAME, b"\0")
        ids.append(nid)
        recs.append(bytes(rec))
        have[nid] = bytes(rec)
        added += 1

    if not added:
        print("  nothing to add")
        return bytes(rom)
    if len(ids) > 0x7E:
        sys.exit(f"{len(ids)} monsters exceeds the raised ceiling")

    out = bytearray(struct.pack(">H", len(ids)))
    out += bytes(ids)
    for r in recs:
        out += r
    packed = lzw_encode.compress(bytes(out))
    if bytes(genesis_ecl.decompress(packed, limit=0x20000)) != bytes(out):
        raise SystemExit("repacked monster stream does not decompress to itself")
    if NEW_STREAM + len(packed) > expand_figures.NEW_DIRECTORY:
        sys.exit("the monster stream would reach the figure directory")
    rom[NEW_STREAM:NEW_STREAM + len(packed)] = packed
    struct.pack_into(">I", rom, STREAM_OPERAND, NEW_STREAM)
    print(f"  {added} creatures added, {len(ids)} monsters total, "
          f"stream {len(packed)} bytes at 0x{NEW_STREAM:06X} (was 0x{at:06X})")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = apply(src.read_bytes())
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

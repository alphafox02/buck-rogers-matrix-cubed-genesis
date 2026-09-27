# SPDX-License-Identifier: MIT
"""
Give the transplanted creatures Matrix Cubed's names.

Monsters cannot simply be transplanted. The two rosters are genuinely
different animals: 54 Genesis records of 214 bytes against 63 DOS records
of 259, and comparing the nineteen names that appear in both shows the
stats do not correspond either -- D.R. WARRIOR is 19/17/17 in DOS and
16/16/15 on the Genesis. Only Buck Rogers lines up, and only on his first
three scores. Converting the records would mean reversing the 214-byte
layout field by field, which has not been done.

`tools/monstermap.py` already substitutes by role, so the fights are the
right shape -- a leader stands in for a leader, a robot for a robot. What
the player sees is the substitute's NAME, so Matrix Cubed's Purge commandos
announce themselves as Terrine leaders.

The name is the first sixteen bytes of the record, NUL padded, and that much
is safe to change: it is read for display and nothing indexes it.

Only slots standing in for exactly ONE Matrix Cubed creature are renamed.
Where several DOS monsters share a Genesis slot there is no single right
name, so those keep Countdown's.

The stream is stored compressed and reached from one place --

    048F0: lea.l $9e77c.l, a0
    048F6: bsr.w $9e76            ; decompress

-- so it is decompressed, edited, repacked and written to expanded ROM with
that one operand retargeted.

Usage:
    rename_monsters.py <in.gen> <out.gen>
"""

import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import genesis_ecl
import integrity
import lzw_encode
import monstermap

STREAM_OPERAND = 0x048F2      # the lea's longword
RECORD = 214
NAME = 16
NEW_STREAM = 0x1B1000         # clear of the picture tables at 0x1B0000


def one_to_one():
    """Genesis slot -> the single Matrix Cubed creature it stands in for."""
    rev = collections.defaultdict(list)
    for dos, val in monstermap.MAP.items():
        gid = val[0] if isinstance(val, tuple) else val
        name = monstermap.DOS_NAMES.get(dos)
        if name:
            rev[gid].append(name)
    return {g: v[0] for g, v in rev.items() if len(set(v)) == 1}


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)
    at = struct.unpack_from(">I", rom, STREAM_OPERAND)[0]
    blob = bytearray(genesis_ecl.decompress(rom[at:at + 0x20000], limit=0x20000))
    count = struct.unpack_from(">H", blob, 0)[0]
    base = 2 + count
    ids = list(blob[2:base])

    want = one_to_one()
    renamed = 0
    for k, gid in enumerate(ids):
        new = want.get(gid)
        if not new:
            continue
        rec = base + k * RECORD
        old = bytes(blob[rec:rec + NAME]).split(b"\0")[0].decode(errors="replace")
        if old == new:
            continue
        if len(new) > NAME - 1:
            print(f"    0x{gid:02X} {new!r} too long for the field, left as {old!r}")
            continue
        blob[rec:rec + NAME] = new.encode("ascii", "replace").ljust(NAME, b"\0")
        print(f"    0x{gid:02X} {old:16} -> {new}")
        renamed += 1

    packed = lzw_encode.compress(bytes(blob))
    check = genesis_ecl.decompress(packed, limit=0x20000)
    if bytes(check) != bytes(blob):
        raise SystemExit("repacked monster stream does not decompress to itself")
    rom[NEW_STREAM:NEW_STREAM + len(packed)] = packed
    struct.pack_into(">I", rom, STREAM_OPERAND, NEW_STREAM)
    print(f"  {renamed} of {count} monsters renamed; stream {len(packed)} bytes "
          f"at 0x{NEW_STREAM:06X} (was 0x{at:06X})")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = apply(src.read_bytes())
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

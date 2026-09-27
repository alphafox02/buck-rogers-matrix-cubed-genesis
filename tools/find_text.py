# SPDX-License-Identifier: MIT
"""
Locate string tables in the Genesis Countdown to Doomsday ROM.

The engine stores text as a table of 16-bit big-endian offsets, each
self-relative to the table's own start address, pointing at NUL-terminated
ASCII. The table is immediately followed by the string data it indexes, so
entry[0] always equals the table length in bytes -- which makes these
tables self-describing and easy to find reliably.

Genesis text is plain ASCII. This is a departure from the DOS games, which
pack four 6-bit characters into three bytes.
"""

import struct
import sys
from pathlib import Path

PRINTABLE = set(range(0x20, 0x7F)) | {0x0A, 0x0D}


def read_string(rom: bytes, pos: int, limit: int = 512):
    out = bytearray()
    while pos < len(rom) and len(out) < limit:
        b = rom[pos]
        if b == 0:
            return bytes(out)
        if b not in PRINTABLE:
            return None
        out.append(b)
        pos += 1
    return None


def table_at(rom: bytes, base: int):
    """
    Validate a self-relative string table at `base`.

    Returns (entry_count, [strings]) or None. entry[0] must point exactly to
    the end of the table, every offset must land past the table, and every
    target must be a readable ASCII string.

    Offsets are NOT monotonic -- the engine deduplicates and shares strings,
    so tables routinely point backwards into text they already indexed.
    """
    if base + 2 > len(rom):
        return None
    first = struct.unpack_from(">H", rom, base)[0]
    if first < 4 or first % 2 or base + first > len(rom):
        return None
    count = first // 2
    if count < 8:
        return None

    offsets = struct.unpack_from(f">{count}H", rom, base)
    if offsets[0] != first:
        return None
    strings = []
    for off in offsets:
        if off < first:
            return None
        s = read_string(rom, base + off)
        if s is None:
            return None
        strings.append(s.decode("ascii"))

    # Reject noise: a real table is mostly non-empty strings of real length.
    filled = [s for s in strings if s]
    if len(filled) < count * 0.5:
        return None
    if sum(len(s) for s in filled) / len(filled) < 2.0:
        return None
    return count, strings


def scan(rom: bytes, min_entries=16):
    """Find every plausible string table in the ROM."""
    found = []
    pos = 0
    while pos < len(rom) - 2:
        result = table_at(rom, pos)
        if result and result[0] >= min_entries:
            count, strings = result
            offsets = struct.unpack_from(f">{count}H", rom, pos)
            end = pos + max(offsets) + max(len(s) for s in strings) + 1
            found.append((pos, count, strings))
            pos = end
        else:
            pos += 2
    return found


if __name__ == "__main__":
    rom = Path(sys.argv[1] if len(sys.argv) > 1 else "roms/countdown.gen").read_bytes()
    tables = scan(rom)
    total = sum(t[1] for t in tables)
    print(f"{len(tables)} string tables, {total} strings\n")
    for base, count, strings in tables:
        sample = " | ".join(s for s in strings[:6] if s)[:88]
        print(f"  0x{base:05X}  {count:5d} entries   {sample}")

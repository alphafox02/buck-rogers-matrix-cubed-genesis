# SPDX-License-Identifier: MIT
"""
Grow the cartridge and relocate its resources into the new space.

The anti-tamper sum at 0x0FFFB0 covers only the first megabyte, and BlastEm's
ROM database maps the cartridge through 0x1FFFFF, so 0x100000 upward is
addressable, unchecked and free. That is where content too large for its
original footprint goes.

Resources are relocated by rewriting the pointer the loader reads, not by
moving code:

    ECL bytecode   32-bit pointer at 0x38CE2 -> stream 1 offset table
    ECL text       32-bit pointer at 0x42B0A -> stream 2 offset table
    Dungeon maps   operand of the lea at 0x0576E

Each ECL stream is a table of 32-bit self-relative offsets followed by its
compressed blocks, so a relocated stream is self-contained: write the table
and data at the new address and point at it.
"""

import struct
from pathlib import Path

import genesis_ecl
import genesis_geo
import integrity
import lzw_encode

# The id list may extend past its original terminator into the space the
# stream-1 offset table used to occupy. Bounded conservatively.
ID_LIST_ROOM = 0x80

EXPANDED = 0x200000
NEW_BASE = 0x100000
HEADER_ROM_END = 0x1A4
GEO_POINTER = 0x05770


class Builder:
    """Accumulates relocated resources in the space above 1 MB."""

    def __init__(self, rom: bytes):
        self.rom = bytearray(rom)
        if len(self.rom) < EXPANDED:
            self.rom += bytearray(b"\xFF" * (EXPANDED - len(self.rom)))
        self.cursor = NEW_BASE

    def place(self, blob: bytes) -> int:
        """Write a blob into free space and return its address."""
        addr = self.cursor
        if addr + len(blob) > EXPANDED:
            raise SystemExit("out of expanded ROM space")
        self.rom[addr:addr + len(blob)] = blob
        self.cursor = (addr + len(blob) + 3) & ~3
        return addr

    def relocate_ecl(self, blocks):
        """`blocks` is [(id, code_bytes, text_bytes)], decompressed."""
        ids = [b[0] for b in blocks]
        for pointer, index in ((genesis_ecl.STREAM1_PTR, 1),
                               (genesis_ecl.STREAM2_PTR, 2)):
            chunks = [lzw_encode.compress(b[index]) for b in blocks]
            table = len(chunks) * 4
            offsets, pos = [], table
            for chunk in chunks:
                offsets.append(pos)
                pos += len(chunk)
            blob = bytearray(struct.pack(f">{len(offsets)}I", *offsets))
            for chunk in chunks:
                blob += chunk
            addr = self.place(bytes(blob))
            struct.pack_into(">I", self.rom, pointer, addr)
            print(f"  ECL stream {index}: {len(blob)} bytes -> 0x{addr:06X}")
        # The id list stays at its hardcoded address but may GROW. The loader
        # at 0x040CE scans it until 0xFF, so extra ids are found simply by
        # being there -- and the space after the terminator holds the
        # ORIGINAL stream-1 offset table, which is dead once 0x38CE2 points
        # at the relocated one. That gives room for far more than the 27
        # areas Countdown shipped with, which matters because Matrix Cubed
        # has 33.
        limit = genesis_ecl.ID_LIST + ID_LIST_ROOM
        if genesis_ecl.ID_LIST + len(ids) + 1 > limit:
            raise SystemExit(f"id list needs {len(ids) + 1} bytes, room is {ID_LIST_ROOM}")
        for k, area in enumerate(ids):
            self.rom[genesis_ecl.ID_LIST + k] = area
        self.rom[genesis_ecl.ID_LIST + len(ids)] = 0xFF

    def relocate_geo(self, stream: bytes):
        addr = self.place(lzw_encode.compress(stream))
        struct.pack_into(">I", self.rom, GEO_POINTER, addr)
        print(f"  GEO stream -> 0x{addr:06X}")

    def finish(self) -> bytes:
        struct.pack_into(">I", self.rom, HEADER_ROM_END, EXPANDED - 1)
        used = self.cursor - NEW_BASE
        print(f"  expanded space used: {used} of {EXPANDED - NEW_BASE} bytes")
        return integrity.repair(bytes(self.rom))


def read_geo_stream(rom: bytes) -> bytes:
    ptr = struct.unpack_from(">I", rom, GEO_POINTER)[0]
    return genesis_ecl.decompress(rom[ptr:], limit=0x20000)


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "roms/countdown.gen")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "roms/countdown_expanded.gen")
    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    geo = read_geo_stream(rom)
    print(f"relocating {len(blocks)} ECL blocks and the GEO stream")
    b = Builder(rom)
    b.relocate_ecl(blocks)
    b.relocate_geo(geo)
    out = b.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

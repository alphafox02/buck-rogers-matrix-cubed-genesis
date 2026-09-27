# SPDX-License-Identifier: MIT
"""
Read the Genesis wall resources, the containers the port must eventually
carry Matrix Cubed's own corridors in.

The wall-set loader is a jump table of 16-bit offsets at 0x083D8, indexed
by the set number:

    0083C8  asl.w   #$1, d3
    0083CA  lea.l   $83d8.l, a0
    0083D0  move.w  (a0, d3.w), d0
    0083D4  jmp     (a0, d0.w)

and each case loads one or two resources, each through `bsr.w $9DD4` --
the same LZW the ECL and geometry streams use, which is why the headers
look like nonsense until they are decompressed.

    set 3   0x0918A8 -> [0xB53E]   0x0EBE89 -> [0xB542]
    set 4   0x06B888 -> [0xB536]   0x0ECFCE -> [0xB53A]
    set 5   0x06B888 -> [0xB536]   0x09B47A -> [0xB53A]

Decompressed, a resource is

    u16   tile count
    u16   nametable length, in bytes
    u16   zero
    ...   nametable: ordinary Genesis words, palette and flip bits in the
          top five, tile index in the low eleven -- so half as many cells
          as bytes
    ...   tile count * 32 bytes, 4bpp 8x8 tiles

which accounts for every byte of all five: 6 + nametable + 32 * tiles is
exactly the decompressed length in each case.

Usage:
    genwall.py [rom]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import genesis_ecl

REPO = Path(__file__).resolve().parent.parent
HEADER = 6
TILE = 32

# set -> the resources its loader case installs
SETS = {3: (0x0918A8, 0x0EBE89),
        4: (0x06B888, 0x0ECFCE),
        5: (0x06B888, 0x09B47A)}


def read(rom: bytes, addr: int):
    """(tiles, nametable, raw) for the resource at `addr`."""
    raw = genesis_ecl.decompress(rom[addr:], limit=0x20000)
    count = struct.unpack_from(">H", raw, 0)[0]
    ntlen = struct.unpack_from(">H", raw, 2)[0]
    nt = raw[HEADER:HEADER + ntlen]          # words, not bytes
    body = raw[HEADER + ntlen:]
    tiles = [body[i * TILE:(i + 1) * TILE] for i in range(count)]
    return tiles, nt, raw


def cells(nt):
    """The nametable as Genesis words."""
    return [struct.unpack_from(">H", nt, i)[0] for i in range(0, len(nt), 2)]


def build(tiles, nametable):
    """The container for a set of 8x8 tiles and a nametable of words."""
    out = bytearray(struct.pack(">HHH", len(tiles), len(nametable), 0))
    out += bytes(nametable)
    for t in tiles:
        out += bytes(t).ljust(TILE, b"\0")[:TILE]
    return bytes(out)


if __name__ == "__main__":
    rom = Path(sys.argv[1] if len(sys.argv) > 1
               else REPO / "roms/matrix_play.gen").read_bytes()
    seen = {}
    for s, addrs in sorted(SETS.items()):
        for a in addrs:
            if a in seen:
                continue
            tiles, nt, raw = read(rom, a)
            ok = HEADER + len(nt) + TILE * len(tiles) == len(raw)
            seen[a] = True
            print(f"  set {s} 0x{a:06X}: {len(tiles):3d} tiles, "
                  f"nametable {len(nt):4d} bytes, {len(raw):5d} total"
                  f"  {'exact' if ok else 'MISMATCH'}")

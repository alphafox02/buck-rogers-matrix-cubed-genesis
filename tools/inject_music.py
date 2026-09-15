"""
Put Matrix Cubed's music into the Genesis ROM.

The driver resolves a music track through a table of 32-bit pointers at
`0x1BAC0`, reached when bit 7 of the kind byte at `0x1B9D4` is set --
`SOUND 0x2E`, the title, is kind `0x82`, so music slot 2.

Each entry points straight at an event stream, so replacing a track is
writing the converted bytes somewhere free and repointing one longword. The
table is inside the checksummed region, so the sum is repaired afterwards.

The Z80 streams a track through a 1 KB ring buffer, fetching from 68k ROM
through the bank register at `0x6000` with the address held at Z80
`0x017E`-`0x0180`. That is a full 24-bit address, so music placed in
expanded ROM above 1 MB is reachable.

Usage:
    inject_music.py <in.gen> <out.gen> <slot>:<file.xmi>:<song> ...
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity
import xmi
import xmi2seq

MUSIC_TABLE = 0x1BAC0
MUSIC_BASE = 0x190000        # below the artwork at 0x1C0000


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst, specs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    rom = bytearray(src.read_bytes())

    cursor = MUSIC_BASE
    for spec in specs:
        slot, path, song = spec.split(":")
        slot, song = int(slot, 0), int(song, 0)
        data = (REPO / "dos_game" / "matrix" / path).read_bytes()
        got = xmi.songs(data)
        if song >= len(got):
            sys.exit(f"{path} has {len(got)} songs, asked for {song}")
        b, e = got[song]
        events = xmi.events(data, b, e)
        seq = xmi2seq.convert(events)
        old = struct.unpack_from(">I", rom, MUSIC_TABLE + slot * 4)[0]
        rom[cursor:cursor + len(seq)] = seq
        struct.pack_into(">I", rom, MUSIC_TABLE + slot * 4, cursor)
        notes = sum(1 for _, st, _ in events if st & 0xF0 == 0x90)
        print(f"  music[{slot}] <- {path} song {song}: {notes} notes, "
              f"{len(seq)} bytes at 0x{cursor:06X} (was 0x{old:06X})")
        cursor += len(seq) + 2

    out = integrity.repair(bytes(rom))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

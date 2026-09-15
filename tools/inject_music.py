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
# In the FIRST megabyte, where every stock track lives. Music placed in
# expanded ROM at 0x190000 crashed the game in play while the same build
# without music was fine, and the difference worth suspecting is that the
# 68000 primes the Z80's ring buffer from here (0x1B824) and refills it as
# the Z80 drains -- a path that may assume music is where it has always been.
# 0x0F1BD8 begins 57 KB of unused space ending just below the checksum
# routine at 0x0FFFB0.
MUSIC_BASE = 0x0F2000

# A track is preceded by a longword giving where it ends. The 68000 reads it
# on the way to the Z80 and nothing works without it:
#
#     1B656: movea.l d0, a0
#     1B658: move.l  -$4(a0), $d8ee.w
#
# Every stock track has one -- 0x0360D8 is followed by 0x800 bytes and its
# preceding longword is 0x0368D8 -- and injecting without it left the driver
# reading a garbage end address and playing nothing at all.
END_POINTER = 4

# The region must be a whole number of 0x100-byte pages, and at least four of
# them. The 68000 feeds the Z80's ring one page at a time and tests for the
# end with an equality compare:
#
#     1B7E8: move.w  #$ff, d0
#     1B7EC: bsr.w   $1b6ca            ; copy 0x100 bytes, a1 -> ring
#     1B7F8: cmpa.l  $d8ee.w, a1       ; end reached?
#     1B7FC: bne.b   $1b804
#     1B7FE: move.l  $d8ea.w, $d8e2.w  ; loop back to the start
#
# so `a1` only ever lands on start + n*0x100. A region whose length is not a
# multiple of that is stepped straight over, and the driver goes on streaming
# whatever follows the track into the FM chip -- static, then a hang. The
# four-page minimum is because 0x1B824 primes the ring with 0x400 bytes
# before the first refill, overshooting any region shorter than that.
# Every stock track obeys both rules: 0x400, 0x500, 0x600, 0x700 or 0x800.
PAGE = 0x100
MIN_PAGES = 4


def pad(seq):
    """Round a converted track up to a whole number of pages."""
    want = max(MIN_PAGES * PAGE, (len(seq) + PAGE - 1) // PAGE * PAGE)
    # Padding sits after the track's own 0xFC terminator, so it is never
    # interpreted; zero is a no-op delta in any case.
    return seq + bytes(want - len(seq))


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
        seq = pad(xmi2seq.convert(events))
        old = struct.unpack_from(">I", rom, MUSIC_TABLE + slot * 4)[0]
        at = cursor + END_POINTER
        struct.pack_into(">I", rom, cursor, at + len(seq))
        rom[at:at + len(seq)] = seq
        struct.pack_into(">I", rom, MUSIC_TABLE + slot * 4, at)
        notes = sum(1 for _, st, _ in events if st & 0xF0 == 0x90)
        print(f"  music[{slot}] <- {path} song {song}: {notes} notes, "
              f"{len(seq)} bytes ({len(seq)//PAGE} pages) at 0x{at:06X}, "
              f"ends 0x{at + len(seq):06X} "
              f"(was 0x{old:06X})")
        cursor = at + len(seq) + 4

    out = integrity.repair(bytes(rom))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

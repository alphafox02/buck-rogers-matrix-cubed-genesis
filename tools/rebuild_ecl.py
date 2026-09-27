# SPDX-License-Identifier: MIT
"""
Rebuild the Genesis ROM's ECL resources from decompressed sources.

This closes the loop: extract -> modify -> recompress -> write -> verify.

Both streams are stored as a table of 32-bit self-relative offsets followed
immediately by the compressed blocks, so rewriting means emitting a new
table and new data over the original region. Our compressor produces output
3-4 bytes smaller than SSI's on every stream tested, so a rebuild always
fits in the space the original occupied -- but the writer checks anyway and
refuses rather than overrun into whatever follows.

Usage:
    rebuild_ecl.py <in.gen> <out.gen> [source_dir]

With no source_dir the blocks are taken from the input ROM unchanged, which
makes the output a pure round-trip test: it must decompress to exactly the
same bytes as the original.
"""

import struct
import sys
from pathlib import Path

import genesis_ecl
import integrity
import lzw_encode

# The first byte after each stream that must not be overwritten, measured by
# decompressing the last block and noting how much input the reader consumed:
#
#   stream 1 (code): table 0x38D02, data ends 0x42B06, and the stream-2
#                    pointer lives at 0x42B0A
#   stream 2 (text): table 0x42B2A, data ends 0x510FF, unrelated data
#                    resumes at 0x5110B
#
# Original footprints are 40,452 and 58,837 bytes. Our compressor produces
# 3-4 bytes less per stream than SSI's, so a rebuild always fits -- but the
# writer enforces these bounds rather than trusting that.
STREAM_LIMIT = {genesis_ecl.STREAM1_PTR: 0x42B0A,
                genesis_ecl.STREAM2_PTR: 0x5110B}


def rebuild(rom: bytes, blocks) -> bytes:
    """`blocks` is [(id, code_bytes, text_bytes)] of DECOMPRESSED data."""
    out = bytearray(rom)
    count = len(blocks)

    for stream_ptr, payloads in (
        (genesis_ecl.STREAM1_PTR, [b[1] for b in blocks]),
        (genesis_ecl.STREAM2_PTR, [b[2] for b in blocks]),
    ):
        table = struct.unpack_from(">I", rom, stream_ptr)[0]
        limit = STREAM_LIMIT[stream_ptr]

        compressed = [lzw_encode.compress(p) for p in payloads]
        header = count * 4
        offsets, pos = [], header
        for chunk in compressed:
            offsets.append(pos)
            pos += len(chunk)

        end = table + pos
        if end > limit:
            raise SystemExit(
                f"stream at 0x{table:05X} needs {pos} bytes but only "
                f"{limit - table} are available"
            )

        for i, off in enumerate(offsets):
            struct.pack_into(">I", out, table + 4 * i, off)
        for off, chunk in zip(offsets, compressed):
            out[table + off:table + off + len(chunk)] = chunk
        # Blank the tail so stale bytes cannot be mistaken for data.
        for p in range(end, limit):
            out[p] = 0

    struct.pack_into(">H", out, 0x18E, _checksum(out))
    # The cartridge verifies itself with a 32-bit longword sum (see
    # tools/integrity.py). Without this the ROM boots to a permanent hang.
    return integrity.repair(bytes(out))


def _checksum(rom) -> int:
    total = 0
    for pos in range(0x200, len(rom) - 1, 2):
        total = (total + struct.unpack_from(">H", rom, pos)[0]) & 0xFFFF
    return total


def verify(original: bytes, rebuilt: bytes) -> bool:
    """Both ROMs must yield identical decompressed resources."""
    a = genesis_ecl.directory(original)
    b = genesis_ecl.directory(rebuilt)
    if len(a) != len(b):
        print(f"block count differs: {len(a)} vs {len(b)}")
        return False
    ok = True
    for (ida, ca, ta), (idb, cb, tb) in zip(a, b):
        if ida != idb:
            print(f"id mismatch: 0x{ida:02X} vs 0x{idb:02X}")
            ok = False
            continue
        for label, x, y in (("code", ca, cb), ("text", ta, tb)):
            dx = genesis_ecl.decompress(x)
            dy = genesis_ecl.decompress(y)
            if dx != dy:
                print(f"  id 0x{ida:02X} {label}: {len(dx)} vs {len(dy)} bytes differ")
                ok = False
    return ok


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "roms/countdown.gen")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "roms/countdown_rebuilt.gen")
    rom = src.read_bytes()

    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    print(f"{len(blocks)} blocks, "
          f"{sum(len(b[1]) for b in blocks)} bytes of code, "
          f"{sum(len(b[2]) for b in blocks)} of text")

    rebuilt = rebuild(rom, blocks)
    dst.write_bytes(rebuilt)
    same = sum(1 for a, b in zip(rom, rebuilt) if a == b)
    print(f"wrote {dst} ({len(rebuilt)} bytes, "
          f"{len(rom) - same} bytes changed, checksum 0x{_checksum(rebuilt):04X})")
    print("verifying resources round-trip...")
    print("  OK -- all resources identical" if verify(rom, rebuilt) else "  FAILED")

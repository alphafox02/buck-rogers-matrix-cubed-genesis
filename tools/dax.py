# SPDX-License-Identifier: MIT
"""
DAX container reader for SSI Gold Box game data.

Format was derived from first principles against Buck Rogers: Matrix Cubed
(DOS) and validated across all 27 .DAX files / 611 blocks shipped with the
game. See docs/formats.md for the derivation and evidence.

Container layout
----------------
    u16   index_size_bytes           (little endian)
    N x   9-byte index records, where N = index_size_bytes / 9:
              u8    block_id
              u32   offset           (relative to end of index)
              u16   unpacked_size
              u16   packed_size
    ...    packed block data

Compression
-----------
Byte-oriented RLE over a signed control byte:
    s < 0   -> repeat the NEXT byte (-s) times
    s >= 0  -> copy the next (s + 1) bytes literally

Confidence: CONFIRMED. All 611 blocks across all 27 files decompress to
exactly their declared unpacked_size, and every block's offset+packed_size
chains exactly to the next block and to EOF.
"""

import struct
from pathlib import Path


class DaxError(Exception):
    pass


def read_index(data: bytes):
    """Return (data_base_offset, [(block_id, offset, unpacked, packed), ...])."""
    if len(data) < 2:
        raise DaxError("file too short to contain an index")
    index_size = struct.unpack_from("<H", data, 0)[0]
    if index_size % 9:
        raise DaxError(f"index size {index_size} is not a multiple of 9")
    records = []
    for pos in range(2, 2 + index_size, 9):
        block_id = data[pos]
        offset, unpacked, packed = struct.unpack_from("<IHH", data, pos + 1)
        records.append((block_id, offset, unpacked, packed))
    return 2 + index_size, records


def decompress(packed: bytes, expected: int) -> bytes:
    """Expand one RLE-packed block. `expected` is the declared unpacked size."""
    out = bytearray()
    i = 0
    while i < len(packed) and len(out) < expected:
        control = packed[i]
        i += 1
        signed = control - 256 if control > 127 else control
        if signed < 0:
            if i >= len(packed):
                raise DaxError("truncated run: control byte with no value")
            out += bytes([packed[i]]) * (-signed)
            i += 1
        else:
            out += packed[i:i + signed + 1]
            i += signed + 1
    return bytes(out)


def load(path) -> dict:
    """Read a .DAX file and return {block_id: decompressed_bytes}."""
    data = Path(path).read_bytes()
    base, records = read_index(data)
    blocks = {}
    for block_id, offset, unpacked, packed in records:
        raw = data[base + offset:base + offset + packed]
        block = decompress(raw, unpacked)
        if len(block) != unpacked:
            raise DaxError(
                f"{path} block {block_id}: got {len(block)} bytes, "
                f"declared {unpacked}"
            )
        blocks[block_id] = block
    return blocks


def verify(path) -> tuple:
    """Validate one file. Returns (block_count, ok_count, chain_ok)."""
    data = Path(path).read_bytes()
    base, records = read_index(data)
    ok = 0
    for block_id, offset, unpacked, packed in records:
        raw = data[base + offset:base + offset + packed]
        try:
            if len(decompress(raw, unpacked)) == unpacked:
                ok += 1
        except DaxError:
            pass
    last = records[-1]
    chain_ok = (base + last[1] + last[3]) == len(data)
    return len(records), ok, chain_ok


if __name__ == "__main__":
    import sys
    targets = sys.argv[1:] or sorted(str(p) for p in Path(".").glob("*.DAX"))
    total = good = 0
    for t in targets:
        n, ok, chain = verify(t)
        total += n
        good += ok
        flag = "ok" if (ok == n and chain) else "FAIL"
        print(f"{Path(t).name:16s} blocks={n:4d} decoded={ok:4d} chain={chain} {flag}")
    print(f"\n{good}/{total} blocks decompressed to their declared size")

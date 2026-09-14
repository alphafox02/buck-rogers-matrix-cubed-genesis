"""
Genesis Countdown to Doomsday: ECL resource extraction.

The ROM stores ECL resources as two parallel streams -- bytecode and text --
each a table of 32-bit self-relative offsets, indexed by a shared id list.
Both streams are LZW compressed.

Resource directory (see docs/re_notes.md for the loader disassembly):

    0x38CE6   id list, one byte per block, 0xFF terminated (27 blocks)
    0x38CE2   pointer to stream 1 offset table  -> 0x38D02   (bytecode)
    0x42B0A   pointer to stream 2 offset table  -> 0x42B2A   (text)

Compression is LZW with a variable-width code and an unusual but efficient
disambiguation scheme, transcribed from the routines at 0x09ED8 (main loop)
and 0x0A092 (code reader):

  * Codes are read most-significant-bit first into a 32-bit accumulator.
  * `width` starts at 9, `next` at 0x102, `max` at 0x1FF, `thresh` at 2.
  * Each read takes the top `width - 1` bits as a candidate value. If that
    value is GREATER than `thresh` it is unambiguously a literal and only
    `width - 1` bits are consumed. Otherwise one more bit is consumed and,
    if set, 0x100 is added -- distinguishing literal from dictionary code.
  * `thresh` tracks how many dictionary entries exist beyond 256, so it is
    exactly the range where that ambiguity can occur.
  * Adding an entry increments `next` and `thresh`. When `next` reaches
    `max`, `width` grows (to a ceiling of 12), `max` becomes (1 << width) - 1
    and `thresh` is reset to 0xFFFF, forcing full-width reads until it
    catches up again.

ECL code is addressed from 0x6AF6 -- the RAM destination in the loader at
0x0410E -- so a jump target converts to a block offset by subtracting it.
This mirrors the DOS games, where the base is 0x8000; in both, the five
event hooks sit at the start and `onInit` lands at offset 0x14.
"""

import struct
from pathlib import Path

ID_LIST = 0x38CE6
STREAM1_PTR = 0x38CE2       # bytecode
STREAM2_PTR = 0x42B0A       # text
CODE_BASE = 0x6AF6          # RAM address ECL is loaded to
BUFFER_SIZE = 0x2C00        # decompression buffer size from the loader

MASK = 0xFFFFFFFF
CLEAR, END = 0x100, 0x101


class _Reader:
    """Transcription of the code reader at 0x0A092."""

    __slots__ = ("data", "ptr", "count", "acc")

    def __init__(self, data):
        self.data = data
        self.ptr = 0
        self.count = 0      # d3: bits held in the accumulator
        self.acc = 0        # d4: 32-bit accumulator, filled from the top

    def read(self, width, thresh):
        while self.count <= 0x18:
            byte = self.data[self.ptr] if self.ptr < len(self.data) else 0
            self.ptr += 1
            self.acc = (self.acc | (byte << (0x18 - self.count))) & MASK
            self.count += 8

        value = (self.acc >> (0x21 - width)) & MASK
        used = width
        if value > thresh:
            used -= 1
            self.acc = (self.acc << used) & MASK
        else:
            carry = (self.acc >> (32 - used)) & 1
            self.acc = (self.acc << used) & MASK
            if carry:
                value |= 1 << (used - 1)
        self.count -= used
        return value


def decompress(data: bytes, limit: int = 0x8000) -> bytes:
    """Expand one LZW-compressed ECL stream."""
    reader = _Reader(data)
    width, nxt, thresh, top = 9, 0x102, 2, 0x1FF
    table = {i: bytes([i]) for i in range(256)}
    out = bytearray()
    prev = None

    while len(out) < limit and reader.ptr <= len(data) + 4:
        code = reader.read(width, thresh)
        if code == END:
            break
        if code == CLEAR:
            width, nxt, thresh, top = 9, 0x102, 2, 0x1FF
            table = {i: bytes([i]) for i in range(256)}
            prev = None
            continue

        if code in table:
            entry = table[code]
        elif prev is not None:
            # The ROM branches on `code >= next` (bcs at 0x09F5A), not on
            # equality, and feeds anything at or past the frontier through the
            # same KwKwK path. Mirror that rather than treating it as corrupt.
            entry = prev + prev[:1]
        else:
            raise ValueError(f"bad LZW code 0x{code:03X} at output {len(out)}")
        out += entry

        if prev is not None and nxt <= top:
            table[nxt] = prev + entry[:1]
            nxt += 1
            thresh = (thresh + 1) & 0xFFFF
            if nxt == top and width < 12:
                width += 1
                top = (1 << width) - 1
                thresh = 0xFFFF
        prev = entry

    return bytes(out)


def directory(rom: bytes):
    """Return [(block_id, code_bytes, text_bytes)] for all ECL resources."""
    ids = []
    pos = ID_LIST
    while rom[pos] != 0xFF:
        ids.append(rom[pos])
        pos += 1

    blocks = []
    for stream_ptr in (STREAM1_PTR, STREAM2_PTR):
        table = struct.unpack_from(">I", rom, stream_ptr)[0]
        offsets = [struct.unpack_from(">I", rom, table + 4 * k)[0]
                   for k in range(len(ids))]
        chunks = []
        for k, off in enumerate(offsets):
            start = table + off
            end = table + offsets[k + 1] if k + 1 < len(offsets) else start + 0x4000
            chunks.append(rom[start:end])
        blocks.append(chunks)

    return list(zip(ids, blocks[0], blocks[1]))


if __name__ == "__main__":
    import sys
    rom = Path(sys.argv[1] if len(sys.argv) > 1 else "roms/countdown.gen").read_bytes()
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "extracted/genesis_ecl")
    out_dir.mkdir(parents=True, exist_ok=True)

    total_code = total_text = 0
    for block_id, code, text in directory(rom):
        code_out = decompress(code)
        text_out = decompress(text)
        total_code += len(code_out)
        total_text += len(text_out)
        (out_dir / f"{block_id:02X}.ecl.bin").write_bytes(code_out)
        (out_dir / f"{block_id:02X}.text.bin").write_bytes(text_out)
        print(f"  id 0x{block_id:02X}  code {len(code):5d} -> {len(code_out):6d}   "
              f"text {len(text):5d} -> {len(text_out):6d}")
    print(f"\n{total_code} bytes of bytecode, {total_text} bytes of text -> {out_dir}/")

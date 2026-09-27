# SPDX-License-Identifier: MIT
"""
Record who called a routine, by reading the return address off the stack.

Scanning the ROM for branches to an address finds nothing when the call goes
through a register or a jump table, and that is exactly the case that keeps
mattering on the figure-drawing path. At a routine's entry the return address
is the longword at (a7), so a stub that copies it into work RAM names the
caller with no scanning at all.

    whocalls.py <in.gen> <out.gen> 0xC9B0

Writes the most recent caller to CALLER and the call count to COUNT, and
keeps the first four DISTINCT callers in a small table at SEEN so a routine
reached from several places can be untangled in one run.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

try:
    from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs
    _MD = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
except ImportError:
    _MD = None

STUB = 0x0F1E40
COUNT = 0xFFEF00           # word
CALLER = 0xFFEF04          # longword, most recent
SEEN = 0xFFEF10            # four longwords, distinct callers in arrival order
SEEN_N = 0xFFEF0C          # word, how many slots are filled


def apply(rom: bytes, at: int) -> bytes:
    rom = bytearray(rom)
    take = 6
    if _MD:
        take = 0
        for insn in _MD.disasm(bytes(rom[at:at + 32]), at):
            take += insn.size
            if take >= 6:
                break
    saved = bytes(rom[at:at + take])

    c = bytearray()
    c += b"\x52\x79" + struct.pack(">I", COUNT)            # addq.w #1, count
    c += b"\x2f\x00"                                        # move.l d0, -(a7)
    c += b"\x2f\x01"                                        # move.l d1, -(a7)
    c += b"\x2f\x08"                                        # move.l a0, -(a7)
    c += b"\x20\x2f\x00\x0c"                                # move.l $c(a7), d0  -- the return address
    c += b"\x23\xc0" + struct.pack(">I", CALLER)            # move.l d0, caller
    # Walk the distinct list; add if absent and there is room.
    c += b"\x41\xf9" + struct.pack(">I", SEEN)              # lea seen, a0
    c += b"\x32\x39" + struct.pack(">I", SEEN_N)            # move.w seen_n, d1
    c += b"\x0c\x41\x00\x04"                                # cmpi.w #4, d1
    c += b"\x6c\x14"                                        # bge.b done      (full)
    c += b"\x53\x41"                                        # subq.w #1, d1
    c += b"\x6b\x08"                                        # bmi.b add       (empty)
    #  loop: compare each entry
    c += b"\xb0\x98"                                        # cmp.l (a0)+, d0
    c += b"\x67\x0c"                                        # beq.b done      (already seen)
    c += b"\x51\xc9\xff\xfa"                                # dbra d1, loop
    #  add:
    c += b"\x20\x80"                                        # move.l d0, (a0)
    c += b"\x52\x79" + struct.pack(">I", SEEN_N)            # addq.w #1, seen_n
    #  done:
    c += b"\x20\x5f"                                        # movea.l (a7)+, a0
    c += b"\x22\x1f"                                        # move.l (a7)+, d1
    c += b"\x20\x1f"                                        # move.l (a7)+, d0
    c += saved
    c += b"\x4e\xf9" + struct.pack(">I", at + len(saved))

    rom[STUB:STUB + len(c)] = c
    rom[at:at + len(saved)] = (b"\x4e\xf9" + struct.pack(">I", STUB)
                               + b"\x4e\x71" * ((len(saved) - 6) // 2))
    print(f"  0x{at:05X} -> stub 0x{STUB:06X} ({len(c)} bytes), "
          f"count 0x{COUNT:06X}, last caller 0x{CALLER:06X}, "
          f"distinct 0x{SEEN:06X} (displaced {saved.hex()})")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes(), int(sys.argv[3], 0))
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

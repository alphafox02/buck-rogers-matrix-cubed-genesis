"""
Count how often a routine is entered, by making it say so.

Reading a routine and reasoning about whether it runs has been wrong three
times on the figure-drawing path, so this asks the machine instead. Each
traced routine gets its entry replaced by a jump to a stub that bumps a
counter in work RAM, runs the instructions it displaced, and jumps back.
tools/play.py can then read the counters after a fight.

    tracecalls.py <in.gen> <out.gen> 0xC20E 0xB58A ...

Counters land at COUNTERS + n, one byte each, in the order given.

The displaced bytes must be whole instructions: pass an address whose first
six bytes disassemble cleanly (a `link.w`/`movem.l` prologue does), and the
stub reproduces them verbatim rather than re-encoding anything.
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

STUBS = 0x0F1D00           # below the music at 0x0F2000, above bigfigures
STUBS_LIMIT = 0x0F1F00
COUNTERS = 0xFFEF00        # work RAM the game does not touch
DISPLACED = 6              # a jmp abs.l is six bytes


def apply(rom: bytes, targets) -> bytes:
    rom = bytearray(rom)
    cursor = STUBS
    for n, at in enumerate(targets):
        # Displace whole instructions only -- a jmp needs six bytes, so take
        # instructions until at least six are covered.
        take = DISPLACED
        if _MD:
            take = 0
            for insn in _MD.disasm(bytes(rom[at:at + 32]), at):
                take += insn.size
                if take >= DISPLACED:
                    break
        saved = bytes(rom[at:at + take])
        stub = bytearray()
        # addq.w #1, (counter).l -- long absolute, so any RAM address works.
        # A byte counter wraps at 256 and reads as a small number, which is
        # indistinguishable from "barely called"; that cost an hour once.
        stub += b"\x52\x79" + struct.pack(">I", COUNTERS + n * 2)
        stub += saved
        stub += b"\x4e\xf9" + struct.pack(">I", at + len(saved))
        rom[cursor:cursor + len(stub)] = stub
        rom[at:at + len(saved)] = (b"\x4e\xf9" + struct.pack(">I", cursor)
                                   + b"\x4e\x71" * ((len(saved) - 6) // 2))
        print(f"  0x{at:05X} -> stub 0x{cursor:06X}, counter {n} at "
              f"0x{COUNTERS + n * 2:06X} (displaced {saved.hex()})")
        cursor += len(stub)
    if cursor > STUBS_LIMIT:
        raise SystemExit("stubs run past their region")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes(),
                [int(a, 0) for a in sys.argv[3:]])
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

"""
Apply research patches to the Genesis Countdown to Doomsday ROM.

Patches are described declaratively so every change is auditable and the
original bytes are asserted before writing -- a mismatch means the ROM is a
different revision and the patch is refused.

Genesis ROMs carry a 16-bit checksum at 0x18E, computed as the sum of all
big-endian words from 0x200 to the end of the ROM. Most emulators ignore
it, but we fix it up so patched ROMs stay valid on real hardware.
"""

import struct
import sys
from pathlib import Path

PATCHES = {
    "trace": {
        "desc": "Force the ECL single-step tracer on (NOP the branch that "
                "skips it when RAM $FF9BB9 is zero)",
        "offset": 0x0334E,
        "before": bytes([0x67, 0x04]),   # beq.s +4
        "after":  bytes([0x4E, 0x71]),   # nop
    },
}


def checksum(rom: bytes) -> int:
    total = 0
    for pos in range(0x200, len(rom) - 1, 2):
        total = (total + struct.unpack_from(">H", rom, pos)[0]) & 0xFFFF
    return total


def apply(rom: bytes, names) -> bytes:
    data = bytearray(rom)
    for name in names:
        patch = PATCHES[name]
        off, before, after = patch["offset"], patch["before"], patch["after"]
        actual = bytes(data[off:off + len(before)])
        if actual != before:
            raise SystemExit(
                f"refusing to patch '{name}': expected {before.hex()} at "
                f"0x{off:05X}, found {actual.hex()} -- wrong ROM revision?"
            )
        data[off:off + len(after)] = after
        print(f"  {name}: 0x{off:05X} {before.hex()} -> {after.hex()}  "
              f"({patch['desc']})")
    struct.pack_into(">H", data, 0x18E, checksum(bytes(data)))
    return bytes(data)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("usage: patch_rom.py <in.gen> <out.gen> <patch> [patch...]\n"
                 "patches: " + ", ".join(PATCHES))
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    rom = src.read_bytes()
    print(f"{src.name}: {len(rom)} bytes, checksum 0x{checksum(rom):04X}")
    out = apply(rom, sys.argv[3:])
    dst.write_bytes(out)
    print(f"wrote {dst} ({len(out)} bytes, checksum 0x{checksum(out):04X})")

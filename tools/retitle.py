"""
Rename the cartridge.

The Genesis header carries the game's name twice, in fixed 48-byte fields
that pad with spaces. Emulators and flash carts read them, so this is what
shows in a title bar or a cartridge menu -- BlastEm was still calling the
build "Buck Rogers: Countdown to Doomsday".

    0x100  16  console name
    0x110  16  copyright, "(C)T-50 1991.DEC"
    0x120  48  domestic name
    0x150  48  overseas name
    0x180  14  serial

The fields are inside the region the cartridge checksums, so the sum is
repaired afterwards. Note the original misspells Rogers as RODGERS; that is
SSI's, and it is not carried over.

Usage:
    retitle.py <in.gen> <out.gen> ["NAME"] ["(C)DATE"]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

DOMESTIC, OVERSEAS, COPYRIGHT = 0x120, 0x150, 0x110
NAME_LEN, COPY_LEN = 48, 16
DEFAULT_NAME = "BUCK ROGERS MATRIX CUBED"
DEFAULT_COPY = "(C)T-50 1992.JAN"


def apply(rom: bytes, name=DEFAULT_NAME, copyright=DEFAULT_COPY) -> bytes:
    rom = bytearray(rom)
    field = name.upper()[:NAME_LEN].ljust(NAME_LEN).encode("ascii")
    for at in (DOMESTIC, OVERSEAS):
        rom[at:at + NAME_LEN] = field
    rom[COPYRIGHT:COPYRIGHT + COPY_LEN] = copyright[:COPY_LEN].ljust(COPY_LEN).encode("ascii")
    print(f"  name      -> {field.decode().strip()!r}")
    print(f"  copyright -> {copyright!r}")
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_NAME
    copy = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_COPY
    out = apply(src.read_bytes(), name, copy)
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

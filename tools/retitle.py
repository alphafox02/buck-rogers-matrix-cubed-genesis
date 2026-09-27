# SPDX-License-Identifier: MIT
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

DOMESTIC, OVERSEAS, COPYRIGHT, SERIAL = 0x120, 0x150, 0x110, 0x180

# The copyright lines the title card prints, in the engine's string pool.
# Countdown is a 1991 title and Matrix Cubed a 1992 one -- its own DOS title
# screen reads "(C)1992 TSR, INC. / (C)1992 THE DILLE FAMILY TRUST / (C)1992
# STRATEGIC SIMULATIONS, INC." -- so the three that name those holders move
# on a year. Same length, so they are edited in place.
#
# "(c) 1991 Electronic arts" is left alone: it credits the Genesis port
# itself, which is what this is built on, and is not part of what the DOS
# game claims.
COPYRIGHT_LINES = (
    b"(c) 1991 TSR, Inc.",
    b"(c) 1991 The Dille Family Trust",
    b"(c) 1991 Strategic Simulations, Inc.",
)
NAME_LEN, COPY_LEN, SERIAL_LEN = 48, 16, 14
DEFAULT_NAME = "BUCK ROGERS MATRIX CUBED"
DEFAULT_COPY = "(C)T-50 1992.JAN"
# The serial is deliberately LEFT ALONE. Emulators look the cartridge up in
# a database by serial before reading the header, which is why BlastEm still
# titles its window "Countdown to Doomsday" whatever the name fields say --
# but that database entry also carries the SRAM mapping, and changing the
# serial to force a miss stopped the game loading. A cosmetic window title
# is not worth the save memory.
DEFAULT_SERIAL = None


def apply(rom: bytes, name=DEFAULT_NAME, copyright=DEFAULT_COPY,
          serial=DEFAULT_SERIAL) -> bytes:
    rom = bytearray(rom)
    field = name.upper()[:NAME_LEN].ljust(NAME_LEN).encode("ascii")
    for at in (DOMESTIC, OVERSEAS):
        rom[at:at + NAME_LEN] = field
    rom[COPYRIGHT:COPYRIGHT + COPY_LEN] = copyright[:COPY_LEN].ljust(COPY_LEN).encode("ascii")
    if serial is not None:
        rom[SERIAL:SERIAL + SERIAL_LEN] = serial[:SERIAL_LEN].ljust(SERIAL_LEN).encode("ascii")
    print(f"  name      -> {field.decode().strip()!r}")
    print(f"  copyright -> {copyright!r}")
    print(f"  serial    -> {serial!r} (unchanged: the emulator ROM database "
          f"keyed on it also supplies the SRAM mapping)")
    moved = 0
    for line in COPYRIGHT_LINES:
        at = bytes(rom).find(line)
        if at < 0:
            continue
        rom[at:at + len(line)] = line.replace(b"1991", b"1992")
        moved += 1
    if moved:
        print(f"  copyright  -> {moved} lines moved from 1991 to 1992")
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

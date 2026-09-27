# SPDX-License-Identifier: MIT
"""
The cartridge's anti-tamper checksum, and how to satisfy it.

Hidden in the last 80 bytes of the ROM at 0x0FFFB0:

    FFFB0  moveq   #$0,d0            ; running sum
    FFFB2  suba.l  a0,a0             ; start at ROM offset 0
    FFFB4  move.l  #$3FFEC,d1        ; 262124 longwords = 0x0FFFB0 bytes
    FFFBA  cmpa.w  #$18C,a0          ; skip the header-checksum longword
    FFFBE  bne.b   $FFFC4
    FFFC0  addq.w  #$4,a0
    FFFC2  bra.b   $FFFC6
    FFFC4  add.l   (a0)+,d0
    FFFC6  subq.l  #$1,d1
    FFFC8  bgt.b   $FFFBA
    FFFCA  cmpi.l  #$10D1310C,d0     ; the expected total
    FFFD0  bne.b   $FFFD4
    FFFD2  rts                       ; pass
    FFFD4  movea.l #$C00004,a4       ; fail: blank the VDP...
    FFFF2  move.w  #$E,$C00000.l     ; ...fill CRAM...
    FFFFE  bra.b   $FFFFE            ; ...and hang forever

A 32-bit sum of every longword in the cartridge except the header checksum
at 0x18C and the routine itself. Any single changed byte anywhere fails it,
and the failure path is a permanent hang -- which is the black screen seen
when booting a rebuilt ROM.

Because the check is a plain additive sum, a modified ROM can be made to
pass again by adjusting one spare longword by the difference. That is
honest repair rather than defeat: the ROM still verifies itself.
"""

import struct

ROUTINE = 0x0FFFB0
LONGWORDS = 0x3FFEC
SKIP = 0x18C
EXPECTED = 0x10D1310C

# A longword inside the largest run of zero padding (17,500 bytes at
# 0x1BBA4), used to absorb the correction. Placed near the end of that run so
# relocated resources can be written at its start without colliding.
SLACK = 0x1FF00

# Usable free space in the same run, for relocating resources that no longer
# fit their original footprint.
FREE_START = 0x1BBA8
FREE_END = 0x1FE00


def checksum(rom: bytes) -> int:
    total = 0
    pos = 0
    for _ in range(LONGWORDS):
        if pos == SKIP:
            pos += 4
            continue
        total = (total + struct.unpack_from(">I", rom, pos)[0]) & 0xFFFFFFFF
        pos += 4
    return total


def verify(rom: bytes) -> bool:
    return checksum(rom) == EXPECTED


def repair(rom: bytes, slack: int = SLACK) -> bytes:
    """Adjust the slack longword so the cartridge checksum passes again."""
    out = bytearray(rom)
    if slack == SKIP or slack >= ROUTINE:
        raise ValueError("slack longword is outside the summed range")
    delta = (EXPECTED - checksum(bytes(out))) & 0xFFFFFFFF
    current = struct.unpack_from(">I", out, slack)[0]
    struct.pack_into(">I", out, slack, (current + delta) & 0xFFFFFFFF)
    if not verify(bytes(out)):
        raise RuntimeError("repair failed to satisfy the checksum")
    return bytes(out)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    src = Path(sys.argv[1])
    rom = src.read_bytes()
    print(f"{src.name}: sum 0x{checksum(rom):08X} "
          f"({'passes' if verify(rom) else 'FAILS'})")
    if len(sys.argv) > 2 and not verify(rom):
        dst = Path(sys.argv[2])
        dst.write_bytes(repair(rom))
        print(f"repaired -> {dst}")

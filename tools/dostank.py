"""
Make an indestructible DOS party, for walking the game rather than playing it.

Comparing the port against the original means reaching places, and the
opening fight for Dr Romney kills a level-7 team. Rather than learn to play
Gold Box combat well, the characters get more hit points than anything in
the scenario can remove.

The character record is `SAVE/<name>.WHO`, 259 bytes, and the fields that
matter were read off a character whose sheet was on screen at the time --
A: STR 15 DEX 15 CON 15 INT 16 WIS 15 CHA 13 TCH 15, 1,000 credits, 40,000
experience, age 20, HP 40/40:

    0x00  name length, then the name
    0x10  the seven abilities, then a second copy at 0x17
    0x2B  credits            u16
    0x2F  experience         u32
    0x38  age                u16
    0x45  hit points         u16   -- and mirrored at 0x9F and 0xE3

This writes NEW characters and never touches the originals.

Usage:
    dostank.py <source name> <new name> [hp]
"""
import shutil
import struct
import sys
from pathlib import Path

SAVE = Path(__file__).resolve().parent.parent / "dos_game/matrix/SAVE"
HP_AT = (0x45, 0x9F, 0xE3)
NAME_AT = 0x00


def make(src: str, new: str, hp: int = 999):
    new = new.upper()[:8]
    for ext in (".WHO", ".STF"):
        s, d = SAVE / f"{src}{ext}", SAVE / f"{new}{ext}"
        if not s.exists():
            raise SystemExit(f"no {s}")
        shutil.copy(s, d)
    who = SAVE / f"{new}.WHO"
    b = bytearray(who.read_bytes())
    b[NAME_AT] = len(new)
    b[NAME_AT + 1:NAME_AT + 1 + 16] = new.encode("ascii").ljust(16, b"\0")
    for off in HP_AT:
        struct.pack_into("<H", b, off, hp)
    who.write_bytes(bytes(b))
    print(f"  {new}: {hp} hit points, from {src}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    make(sys.argv[1], sys.argv[2],
         int(sys.argv[3]) if len(sys.argv) > 3 else 999)

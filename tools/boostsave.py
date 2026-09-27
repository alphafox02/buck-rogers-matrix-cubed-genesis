"""
Boost a party that is already saved, in the emulator's SRAM.

`boostparty.py` edits the team stored in the ROM, which is what you get by
restoring the built-in PREGENERATED TEAM. A game already saved to a slot keeps
its own copy of the characters and never sees that edit -- a play session hit
exactly this, restoring a save made before the boost existed and finding
level 2 and 25 hit points.

The save is the same LZW the rest of the engine uses, with an eight-byte
header, and the party is the first thing in it: six 214-byte records at 0, 214,
428 and so on, the same layout as the ROM blob. Re-packing the untouched
stream reproduces the original file byte for byte, so there is no checksum to
satisfy -- the round trip is checked here before anything is written.

**This does not work yet, and it refuses to write.** The edited save decodes
perfectly and re-packs to the right length, and the game then does not list it
at all -- a play session restored and found the slot simply gone. The last
seventeen bytes of the payload are high entropy where everything around them
is zero:

    ...00 00 00 00  ef 3e d6 69 35 05 cf ac a9 83 0a a5 85 0d 76 0f 10

which is a signature over the save, and nothing here recomputes it. No simple
sum matches: byte sum 0x5ABE and word sum 0x7872 against header words 0x0000,
0x1234, 0x0203, 0x0300, and no 16-bit field in the payload equals the sum of
everything but itself.

Until that is worked out, the way to get a boosted party into a save is to let
the ENGINE write it: restore the built-in PREGENERATED TEAM, which
`boostparty.py` has already edited in the ROM, play, and save to a slot. The
game checksums its own file correctly.

The original file is copied to `<name>.before-boost` first.

Usage:
    boostsave.py <save.sram> [--hero|--veteran]
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import boostparty as bp
import genesis_ecl
import lzw_encode

HEADER = 8
SIZE = 8192
PARTY = 6          # characters; what follows in a save is game state


def apply(raw: bytes, hero=True) -> bytes:
    body = bytearray(genesis_ecl.decompress(raw[HEADER:], limit=0x8000))
    if lzw_encode.compress(bytes(body)) != raw[HEADER:HEADER + len(lzw_encode.compress(bytes(body)))]:
        raise SystemExit("this save does not re-pack to itself; not touching it")
    # The first six records only. A save is not the ROM blob: past the party
    # comes game state, and `records()` walking on into it found a seventh
    # "character" with no name, level 1 and no hit points -- writing a level
    # into that is writing into whatever the engine keeps there.
    for k, off, name in list(bp.records(body))[:PARTY]:
        if hero:
            bp.summary(body, k, bp.hero(body, off, name))
        else:
            bp.summary(body, k, bp.veteran(body, off, name, bp.VETERAN_LEVEL))
    packed = lzw_encode.compress(bytes(body))
    if genesis_ecl.decompress(packed, limit=0x8000) != bytes(body):
        raise SystemExit("the edited save does not round-trip")
    out = bytearray(raw[:HEADER]) + packed
    if len(out) > SIZE:
        raise SystemExit(f"the edited save is {len(out)} bytes, over the {SIZE} SRAM")
    out += b"\x00" * (SIZE - len(out))
    print(f"  save stream {len(raw) and len(packed)} bytes, {SIZE - len(out) + len(out)} total")
    return bytes(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    hero = "--veteran" not in sys.argv[2:]
    backup = path.with_suffix(path.suffix + ".before-boost")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"  original copied to {backup}")
    out = apply(path.read_bytes(), hero)
    if "--i-know-it-will-be-rejected" not in sys.argv[2:]:
        sys.exit("  NOT WRITING: the game rejects an edited save -- see the "
                 "header of this file. Restore the PREGENERATED TEAM instead, "
                 "which boostparty.py has already edited in the ROM.")
    path.write_bytes(out)
    print(f"  wrote {path}")

# SPDX-License-Identifier: MIT
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

**This does not work, and it refuses to write.** Three attempts, each one
ruling something out, and the slot vanishes from the restore list every time
-- not a corrupt save, a missing one:

    what was touched                     stream     result
    records + the summary array at 1712  719 bytes  slot gone
    records only                         721 bytes  slot gone
    records only                         711 bytes  slot gone

The first was a genuine mistake: the 26-byte summary array at 8 * 214 is real
in the ROM BLOB, where the loader copies it to 0xC470, and a save is not the
blob. The other two touched nothing but the six character records, at a stream
both longer and shorter than the original, so it is neither where the edit
lands nor how long the result is.

What is left is the last seventeen bytes of the payload, high entropy where
everything around them is zero:

    ...00 00 00 00  ef 3e d6 69 35 05 cf ac a9 83 0a a5 85 0d 76 0f 10

That is a signature over the save and nothing here recomputes it. No simple
sum matches: the payload sums to 0x5ABE by byte and 0x7872 by word, the header
words are 0x0000, 0x1234, 0x0203 and 0x0300, and no 16-bit field inside equals
the sum of everything but itself.

So the way to get a boosted party into a save is to let the ENGINE write it:
restore the built-in PREGENERATED TEAM, which boostparty.py has already edited
in the ROM and which startkit.py has given the upgraded gear, play, and save.
The game signs its own file correctly.

The other way, not built: patch the ROM to raise the party in RAM after a save
is loaded, which leaves the file alone entirely. That needs the point where a
restore finishes writing 0xFFBA68, which is not yet found.

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
    # ONLY the character records. `boostparty` also writes a 26-byte summary
    # array at 8 * 214 = 1712, which is right for the ROM blob -- the loader
    # copies it to 0xC470 -- but a save is not the blob, and there is no reason
    # to believe 1712 means the same thing in one as in the other. The first
    # attempt wrote there and the game stopped listing the slot.
    for k, off, name in list(bp.records(body))[:PARTY]:
        if hero:
            bp.hero(body, off, name)
        else:
            bp.veteran(body, off, name, bp.VETERAN_LEVEL)
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
    if "--i-know-the-game-will-reject-it" not in sys.argv[2:]:
        sys.exit("  NOT WRITING -- see the header. Restore the PREGENERATED "
                 "TEAM instead: it is boosted in the ROM and carries the "
                 "upgraded kit.")
    path.write_bytes(out)
    print(f"  wrote {path}")

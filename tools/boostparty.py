"""
Give the port's pregenerated team a working perception score.

Matrix Cubed gates its set pieces on skill checks the DOS game expects the
party to sometimes pass. The coronation ambush on the Salvation dock is the
clearest one: pass a Notice check and you are offered WAIT / ATTACK / KNOCK
DOWN THE SUN KING, fail it and the script jumps straight past both the
narration and the menu to the assassination. A play session failed it twice
in a row, which is what prompted looking.

Reading the party out of RAM explains it. The engine keeps characters as
214-byte records from 0xFFBA68 -- the same base the skill check itself uses,
`lea.l $ba68.w, a2` at 0x04F2E -- and skills are one byte each at record
offset 0x31, indexed by skill id, per `move.b $31(a2,d1.w),d4` at 0x04FC6.
Genesis skill 5 is perception, so the byte is record+0x36. The shipped team
reads:

    FLAVIUS 0   CELESTE 0   PIERRE 2   NICHOLE 0   ROARKE 0   JANELLE 0

Only one character has the skill at all. The check takes the party's best, so
every Notice roll in the game has been Pierre's 2 against a die.

The team is stored compressed at 0x06BAAD -- 1920 bytes, six 214-byte records
then two empty slots -- reached by a single `lea.l $6baad.l, a0` at 0x001F32.
So it is editable exactly like the wall art: decompress, edit, recompress,
drop it in free space and repoint the lea.

The engine caps a skill's contribution at twice the character's level
(`move.b $19(a2),d0; asl.b #1,d0` at 0x04FCC), and the team is level 2, so 4
is the highest value that still counts as an ordinary in-range score rather
than an inflated one. That is the ceiling used here.

There is also a `--strong` mode for testing rather than playing. Validating a
transplanted scenario means getting deep enough into it to see the set pieces,
and dying to the coronation ambush eight times does not test anything. It
raises hit points, attributes and every skill together. It is deliberately not
the default: an inflated party hides exactly the difficulty regressions this
port needs to find.

Record fields used here, all confirmed against the creation handlers
documented in docs/re_notes.md (race at $17, career at $18, level at $19,
exp-to-next at $1E, hit die at $26, and the race modifiers at $2A/$2C all read
back correctly on the shipped team):

    +0x10..0x14   attributes
    +0x19         level
    +0x2E         hit points -- [25, 23, 17, 15, 11, 11] on the shipped team,
                  tracking the hit die exactly (warriors 4, the rest 2)
    +0x31         skills, one byte each

Usage:
    boostparty.py <in.gen> <out.gen> [--veteran|--strong] [skill=value ...]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import genesis_ecl
import integrity
import lzw_encode

TEAM = 0x06BAAD             # the compressed party blob
TEAM_LEA = 0x001F34         # the operand of `lea.l $6baad.l, a0`
RECORD = 214
SKILLS = 0x31               # first skill byte within a record
LEVEL = 0x19
FREE, FREE_LIMIT = 0x1BBE00, 0x1C0000

ATTRS = 0x10
ATTR_COUNT = 5
HP = 0x2E

PERCEPTION = 5
DEFAULT = {PERCEPTION: 4}   # the level-2 cap

STRONG_HP = 99
STRONG_ATTR = 18
STRONG_SKILL = 10
# Only the fourteen general skills live in the record's skill array. It runs
# from +0x31, and +0x42 is NOT skill 17 -- it holds a per-character value that
# differs across the team (131, 133, 138, 135, 129, 128), a portrait or figure
# id. Writing 19 skills walks over it.
#
# --strong never noticed because it uses max(), which leaves a byte of 131
# alone. --veteran scales instead, shrank that byte to 12, and the game then
# hung in the opening briefing -- area 0x00, never reaching the dock. Bisecting
# level, hit points and skills separately is what found it: only skills broke.
#
# skillmap groups them the same way: PILOT through PROGRAM is range(14), and
# the weapon skills above that are kept elsewhere.
SKILL_COUNT = 14

# A party at the level Matrix Cubed actually assumes.
#
# Matrix Cubed is Volume II. DOS ships no pregenerated team at all -- CHARS.DAX
# holds no named characters -- because it expects a party imported from
# Countdown to Doomsday, already several levels in. A player who makes a fresh
# team in DOS starts at level 1, which is worse still.
#
# The port inherits Countdown's own pregens instead: level 2, 11 to 25 hit
# points. What the opening dock spawns at them, read out of its script and the
# monster roster:
#
#     8 x RAM ASSASSIN     level 6, 42 hp
#     6 x MER. WARRIOR     level 7, 49 hp
#     5 x MER. H.S. ROBOT  level 7, 77 hp
#     6 x TECHNICIAN       level 4, 16 hp
#
# So level 6 is not a guess -- it is what the first area fights with. Hit
# points scale each character by the same points-per-level they already have,
# which keeps the team's internal balance (the warriors stay the tough ones)
# instead of flattening everyone to one number the way --strong does.
VETERAN_LEVEL = 6


def records(raw):
    for k in range(len(raw) // RECORD):
        off = k * RECORD
        name = raw[off:off + 15].split(b"\x00")[0].decode("ascii", "replace")
        if name:
            yield k, off, name


def veteran(raw, off, name, level):
    """Bring one character up to `level`, keeping its own shape."""
    was = raw[off + LEVEL] or 1
    hp_was = raw[off + HP]
    raw[off + LEVEL] = level
    raw[off + HP] = min(250, round(hp_was / was * level))
    cap = level * 2
    grown = []
    for i in range(SKILL_COUNT):
        at = off + SKILLS + i
        if raw[at]:
            raw[at] = min(cap, round(raw[at] / was * level))
            grown.append(i)
    # Every character needs some perception: the game gates set pieces on it,
    # and a party check takes the best score, so a team of zeroes never passes.
    per = off + SKILLS + PERCEPTION
    raw[per] = max(raw[per], level)
    print(f"  {name:10s} level {was} -> {level}, hp {hp_was} -> {raw[off + HP]}, "
          f"{len(grown)} skills scaled, perception {raw[per]}")


def boost(rom: bytes, want, strong=False, vet=False):
    raw = bytearray(genesis_ecl.decompress(rom[TEAM:], limit=0x8000))
    for _k, off, name in records(raw):
        cap = raw[off + LEVEL] * 2
        if vet:
            veteran(raw, off, name, VETERAN_LEVEL)
            continue
        if strong:
            hp_before = raw[off + HP]
            raw[off + HP] = STRONG_HP
            for i in range(ATTR_COUNT):
                raw[off + ATTRS + i] = max(raw[off + ATTRS + i], STRONG_ATTR)
            for i in range(SKILL_COUNT):
                raw[off + SKILLS + i] = max(raw[off + SKILLS + i], STRONG_SKILL)
            print(f"  {name:10s} hp {hp_before} -> {STRONG_HP}, "
                  f"attributes -> {STRONG_ATTR}, all skills -> {STRONG_SKILL}")
            continue
        line = []
        for skill, value in want.items():
            at = off + SKILLS + skill
            before = raw[at]
            raw[at] = max(before, min(value, cap))
            line.append(f"skill {skill}: {before} -> {raw[at]}")
        print(f"  {name:10s} (level {raw[off + LEVEL]}, cap {cap})  "
              + ", ".join(line))

    packed = lzw_encode.compress(bytes(raw))
    if FREE + len(packed) > FREE_LIMIT:
        raise SystemExit("out of free space for the party")
    out = bytearray(rom)
    out[FREE:FREE + len(packed)] = packed
    struct.pack_into(">I", out, TEAM_LEA, FREE)
    print(f"  party blob {len(raw)} bytes -> {len(packed)} packed at 0x{FREE:06X};"
          f" lea at 0x{TEAM_LEA:06X} repointed")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    strong = "--strong" in sys.argv[3:]
    vet = "--veteran" in sys.argv[3:]
    want = dict(DEFAULT)
    for arg in sys.argv[3:]:
        if "=" in arg:
            k, v = arg.split("=")
            want[int(k)] = int(v)
    out = integrity.repair(boost(src.read_bytes(), want, strong, vet))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

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
    boostparty.py <in.gen> <out.gen> [--veteran|--hero|--strong] [skill=value ...]
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
EXP_NEXT = 0x1E             # experience for the next level, a longword

# The blob holds TWO structures, and the loader at 0x001F3C reads them both:
#
#     0x6B0 bytes -> 0xFFBA68   eight 214-byte character records
#     0xD0  bytes -> 0xFFC470   eight 26-byte entries
#
# 1712 + 208 = 1920, exactly the blob. The second array carries its own copy of
# level and hit points, and editing only the records leaves it stating the old
# ones -- which is how a "level 6" party still read level 2 at 0xC470.
SUMMARY = 8 * RECORD        # where the 26-byte entries start
SUMMARY_SIZE = 26
# +14 is hit points. +16 looked like level -- it reads 2 on a level-2 team --
# but writing 6 there changes nothing: the engine puts it back, so it is
# something it derives rather than stores. Level lives only in the record.
SUM_HP = 14
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
# Level 8, not 6. The first area's creatures are level 7, and comparing hit
# points against DOS (which keeps them at +0x45 of a MON0CHA.DAX record) shows
# 52 of 63 are WEAKER on the Genesis -- but not all of them. The Mercurian
# encounter on the way back to the ship is six MER. WARRIOR at 49 and three
# MER. H.S. ROBOT at 77, and the robots are one of six creatures whose hit
# points are identical to DOS. So that fight arrives at full strength against a
# party that DOS assumed would be imported from Countdown, several levels in.
#
# At 6 the team fields 306 hit points against that encounter's 525. At 8 it is
# 408, which is a hard fight rather than an arithmetic impossibility.
VETERAN_LEVEL = 8

# --hero: for testing a run end to end, not for judging the balance.
#
# --veteran keeps the team's shape and lands it where the first area fights;
# --strong flattens everyone to one number and loses that shape. --hero does
# the levelling FIRST, so the warriors stay the tough ones, and then lifts
# attributes and skills to what a character of that level can hold. The skill
# ceiling is the engine's own: 0x04FCC caps a skill's contribution at twice
# the character's level, so at level 12 anything above 24 is wasted and 16 is
# a high score that still counts.
# 8, not 12. The engine's experience tables at 0x00C36 hold seven thresholds
# per career and then 0xFFFFFFFF, so **level 8 is the highest level the engine
# can express**. A level-12 character is off the end of its own career's table,
# and the trainer -- which exists to turn experience into levels -- was handed
# one and could not be left: it offered advancement picks computed from a level
# it has no row for, and would not close until they were spent.
#
# Reported from play as "I chose to train and now I can't exit the area".
HERO_LEVEL = 8
# Hit points do not have to track the level. They are a single byte at +0x2E
# with no separate maximum anywhere in the record, so clamping the level to 8
# need not cost the party the durability it had at 12. This restores it:
# 12/8, which reproduces the 150/138/102/90/66/66 the level-12 team carried.
HERO_HP_SCALE = 12 / 8
HERO_ATTR = 18
HERO_SKILL = 16


def records(raw):
    for k in range(len(raw) // RECORD):
        off = k * RECORD
        name = raw[off:off + 15].split(b"\x00")[0].decode("ascii", "replace")
        if name:
            yield k, off, name


def summary(raw, k, hp):
    """Keep the 26-byte entry's hit points in step with its record."""
    at = SUMMARY + k * SUMMARY_SIZE
    if at + SUMMARY_SIZE <= len(raw):
        raw[at + SUM_HP] = min(255, hp)


def veteran(raw, off, name, level):
    """Bring one character up to `level`, keeping its own shape."""
    was = raw[off + LEVEL] or 1
    hp_was = raw[off + HP]
    raw[off + LEVEL] = level
    # Experience has to agree with the level or the trainer cannot reconcile
    # them. A character the engine considers finished carries 0xFFFFFFFF in
    # exp-to-next -- that is the terminator each career's table ends with --
    # and at HERO_LEVEL, which is the engine's maximum, that is the honest
    # value. Leaving the pregens' level-2 threshold here is what handed the
    # trainer a level-8 character who still owed six levels of advancement.
    struct.pack_into(">I", raw, off + EXP_NEXT, 0xFFFFFFFF)
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
    return raw[off + HP]


def hero(raw, off, name):
    """Level up first, keeping the character's shape, then raise the rest."""
    hp = veteran(raw, off, name, HERO_LEVEL)
    raw[off + HP] = min(250, round(raw[off + HP] * HERO_HP_SCALE))
    hp = raw[off + HP]
    for i in range(ATTR_COUNT):
        raw[off + ATTRS + i] = max(raw[off + ATTRS + i], HERO_ATTR)
    for i in range(SKILL_COUNT):
        raw[off + SKILLS + i] = max(raw[off + SKILLS + i], HERO_SKILL)
    return hp


def boost(rom: bytes, want, strong=False, vet=False, hro=False):
    raw = bytearray(genesis_ecl.decompress(rom[TEAM:], limit=0x8000))
    for _k, off, name in records(raw):
        cap = raw[off + LEVEL] * 2
        if hro:
            summary(raw, _k, hero(raw, off, name))
            continue
        if vet:
            hp = veteran(raw, off, name, VETERAN_LEVEL)
            summary(raw, _k, hp)
            continue
        if strong:
            hp_before = raw[off + HP]
            raw[off + HP] = STRONG_HP
            for i in range(ATTR_COUNT):
                raw[off + ATTRS + i] = max(raw[off + ATTRS + i], STRONG_ATTR)
            for i in range(SKILL_COUNT):
                raw[off + SKILLS + i] = max(raw[off + SKILLS + i], STRONG_SKILL)
            summary(raw, _k, STRONG_HP)
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
    hro = "--hero" in sys.argv[3:]
    want = dict(DEFAULT)
    for arg in sys.argv[3:]:
        if "=" in arg:
            k, v = arg.split("=")
            want[int(k)] = int(v)
    out = integrity.repair(boost(src.read_bytes(), want, strong, vet, hro))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

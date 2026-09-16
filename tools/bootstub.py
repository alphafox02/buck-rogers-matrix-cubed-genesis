"""
Replace area 0x00 with a boot stub that drops the player into a chosen area.

Neither game's area 0x00 is usable as a boot block for a player. Both are
SSI developer harnesses: their movement hooks jump to a warp menu --

    00D0: PRINT_CLEAR      "WHERE DO YOU WISH TO GO?"
    00FA: MENU_HORIZONTAL  [0x7F79], 7      ; JUMP ARENA DUEL SPACE ...

-- so in Matrix Cubed's block 1 every step the player takes opens that menu,
and picking SPACE launches the ship. Countdown's block 0x00 is the same
shape, which is why retargeting one NEWECL inside it did not help: the
branch a player actually takes falls through into the menu.

The stub replaces the whole block with the shortest thing that works,
mirroring the sequence Countdown's own boot uses when it does reach the
game:

    NEWECL     <area>
    LOADFILES  <area>, 0x7F, 0xFF
    LOADPIECES <wallset>
    SAVE       <y>, [0x9AF7]      ; DUNGEON_Y
    SAVE       <x>, [0x9AF6]      ; DUNGEON_X
    SAVE       <f>, [0x9AFA]      ; DUNGEON_DIR
    NEWREGION  0, 1, 0, 0, 0xF, 0xF
    EXIT

and points all four event hooks at a bare EXIT, so nothing the player does
can re-enter it.

The engine picks its entry area at 0x04146, and there is more than one:

    04146: tst.b   $ba5a.w
    0414A: beq.b   $4154
    0414C:   move.b #$3, $b9f0.w     ; -> area 0x03
    04154: tst.b   $ca21.w
    04158: bne.b   $4160
    0415A:   clr.b  $b9f0.w          ; -> area 0x00
    04160:   move.b #$10, $b9f0.w    ; -> area 0x10   "default team"
    04168: move.b  $97e8.w, $b9f0.w  ; -> the saved area, on a restore
    04174: bsr.w   $40d0

Choosing "load default team" boots area 0x10, so a stub in 0x00 alone is
never reached. The stub goes into every new-game entry.

The map is named separately from the script, because they are not always
the same. A cutscene block carries no geometry of its own -- block 24, the
game's opening, has no map 24 in GEO1 and does `LOAD_AREA_MAP 64` itself --
so `LOADFILES <area>` would ask the engine for a map that does not exist.
Give the map area explicitly in that case; it defaults to the script's area,
which is right for an ordinary room.

Usage:
    bootstub.py <in.gen> <out.gen> <area> <wallset> <x> <y> [map] [facing]
                [--intro] [--marker]
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

import expand
import genesis_disasm as G
import genesis_ecl
import integrity

DUNGEON_X, DUNGEON_Y, DUNGEON_DIR = 0x9AF6, 0x9AF7, 0x9AFA

# Areas the engine will boot into for a new game, from the dispatch above.
ENTRIES = (0x00, 0x10)


def _imm(v):
    if v <= 0xFF:
        return bytes([0x00, v])
    return bytes([0x02]) + struct.pack("<H", v)


def _mem(v):
    return bytes([0x01]) + struct.pack("<H", v & 0xFFFF)


MARKER = b"*** MATRIX CUBED BOOT STUB ***"

# The DOS game opens on a briefing before it drops the player into the
# coronation, and the Genesis build went straight to the room. The text is
# Matrix Cubed's own, lifted verbatim from block 19 at 0x0568 onward.
#
# It lives here rather than in block 19 because entering that block is not
# safe: it never does NEWECL -- it IS the script for that stretch -- and its
# movement hook is the ship, so a player who can move walks into space. The
# stub runs before anyone can move, which is exactly what this needs.
#
# Pictures 101 and 57 are ids Countdown does not carry, so they substitute;
# SOUND 0x30 is where tools/soundmap.py sends the cue block 19 fires here.
# The kit the DOS game hands the party at the end of the briefing, straight
# from block 19: `CLEAR_MON`, `TREASURE 8000, 20, {...}`, `COMBAT`.
#
# All three matter. TREASURE only fills a buffer -- credits to 0xBA34, the
# count to 0xB9F3 and the ids to 0xB9F4 -- and shows nothing:
#
#     0392C: bsr.w  $404a          ; credits
#     03934: bsr.w  $404a          ; count
#     0393E: lea.l  $b9f4.w, a3    ; the item list
#     03964: move.b d0, (a3)+      ; each id in turn
#     03976: rts
#
# COMBAT is what presents the take-and-divvy screen. Every one of the five
# TREASURE calls in Countdown's own scripts is followed immediately by
# COMBAT, and so is block 19's. Without it the kit is handed over invisibly
# and the player never sees an item.
#
# CLEARMONSTERS first, so COMBAT has nothing to fight and goes straight to
# the spoils, which is what block 19 relies on too.
#
# The item ids need no translation. Both games' item tables are the same 91
# entries in the same order -- the DOS one is 16-byte records in
# ITEM0.DAX, the Genesis one 10-byte records at 0xF17D8, and decoding both
# through the name fragments gives 91 of 91 identical, from "knife" at 1 to
# "mercurian battle armor" at 88. Of everything transplanted so far this is
# the only table that matched outright.
# And what block 19 prints after the kit, on the way into the coronation --
# `PRINT_CLEAR` at 0x076A, immediately before its `NEW_ECL 17` at 0x07CB.
ARRIVAL = ("YOU STEP OUT ONTO THE EXPANSIVE DOCK AND FIND IT THRONGED WITH "
           "PEOPLE DRESSED FOR THE CORONATION. A MAN APPROACHES.")

STARTING_CREDITS = 8000
STARTING_KIT = [22, 22, 22, 22, 23, 23, 33, 33, 33, 8,
                8, 15, 6, 6, 6, 18, 10, 10, 35, 35]

INTRO_MUSIC = 0x30
INTRO = [
    (101, "YOU EASE INTO ORBIT AROUND MERCURY AND FLIP THE COM SWITCH FOR A "
          "FINAL BRIEFING. THE IMAGE OF BUCK ROGERS, NOW IN CHARGE OF SPECIAL "
          "MISSIONS, APPEARS ONSCREEN."),
    (57,  "'I KNOW YOU'RE ITCHING TO PULL MORE COMBAT DUTY INSTEAD OF "
          "BABYSITTING THIS NEW SUN KING, LORD BERKELEY, BUT THIS MISSION IS "
          "CRITICAL."),
    (None, "'BERKELEY IS CALLING FOR A BROTHERHOOD BETWEEN ALL RACES. NOT "
           "EVERYONE LIKES THE IDEA. PROTECT HIM FROM ANY ASSASSINATION "
           "ATTEMPTS."),
    (None, "'IF BERKELEY SUCCEEDS, WE WILL HAVE A UNITED FRONT AGAINST RAM. "
           "TRY TO FORGE THIS NEW ALLIANCE. GOOD LUCK TEAM!'"),
]


def _intro_pool():
    """Text pool for the briefing, and each screen's offset into it.

    Returns (pool, before, after) -- the screens that play before the
    starting kit is handed over, and the arrival text that follows it.
    """
    import transpile
    pool = bytearray(b"\0")
    before, after = [], []
    for pic, text in INTRO:
        for k, chunk in enumerate(transpile._split(text)):
            before.append((pic if k == 0 else None, len(pool)))
            pool += chunk.encode("ascii", "replace") + b"\0"
    for chunk in transpile._split(ARRIVAL):
        after.append((None, len(pool)))
        pool += chunk.encode("ascii", "replace") + b"\0"
    return bytes(pool), before, after


def build(area, wallset, x, y, map_area=None, facing=0, marker=False,
          intro=False):
    table = G.load_opcodes()
    op = {n: o for o, (n, _) in table.items()}

    # Five hooks, each a GOTO: opcode plus a 3-byte memory operand.
    HOOK = 4
    exit_at = 5 * HOOK
    init_at = exit_at + 1

    out = bytearray()
    for _ in range(4):                       # move / search / rest / ...
        out += bytes([op["GOTO"]]) + _mem(G.CODE_BASE + exit_at)
    out += bytes([op["GOTO"]]) + _mem(G.CODE_BASE + init_at)
    assert len(out) == exit_at
    out += bytes([op["EXIT"]])
    assert len(out) == init_at

    if marker:
        # A one-look answer to "is this ROM actually booting through area
        # 0x00?". Printed before anything else the stub does.
        out += bytes([op["PRINTCLEAR"]]) + bytes([0x80]) + struct.pack("<H", 1)
        out += bytes([op["CONTINUE"]])
    # The briefing plays BEFORE the area is set up, and has to.
    #
    # Moving it after NEWECL/NEWREGION was tried, to get it drawn over the
    # ordinary game screen -- picture window, party roster, text box -- the
    # way the DOS game shows it. Nothing played at all: the player went
    # straight from "begin adventure" into the room. Setting up the region
    # hands control to the area, and whatever the stub still has queued
    # after that never runs.
    #
    # So it runs first, over the team-select screen, which means text across
    # the top with the empty character slots showing through and nowhere for
    # PICTURE to draw. Plain, but it happens -- and a briefing that plays
    # beats a better-looking one that does not.
    if intro:
        _, before, after = _intro_pool()

        def screen(pic, at):
            if pic is not None:
                out.extend(bytes([op["PICTURE"]]) + _imm(pic))
            out.extend(bytes([op["PRINTCLEAR"]]) + bytes([0x80])
                       + struct.pack("<H", at))
            out.extend(bytes([op["CONTINUE"]]))

        out += bytes([op["SOUND"]]) + _imm(INTRO_MUSIC)
        for pic, at in before:
            screen(pic, at)
        out += bytes([op["CLEARMONSTERS"]])
        out += bytes([op["TREASURE"]]) + _imm(STARTING_CREDITS) \
            + _imm(len(STARTING_KIT)) + b"".join(_imm(i) for i in STARTING_KIT)
        out += bytes([op["COMBAT"]])
        for pic, at in after:
            screen(pic, at)

    out += bytes([op["NEWECL"]]) + _imm(area)
    out += bytes([op["LOADFILES"]]) + _imm(area if map_area is None else map_area) \
        + _imm(0x7F) + _imm(0xFF)
    out += bytes([op["LOADPIECES"]]) + _imm(wallset)
    out += bytes([op["SAVE"]]) + _imm(y) + _mem(DUNGEON_Y)
    out += bytes([op["SAVE"]]) + _imm(x) + _mem(DUNGEON_X)
    out += bytes([op["SAVE"]]) + _imm(facing) + _mem(DUNGEON_DIR)
    out += bytes([op["NEWREGION"]]) + b"".join(
        _imm(v) for v in (0, 1, 0, 0, 0x0F, 0x0F))
    out += bytes([op["EXIT"]])
    return bytes(out)


def main():
    if len(sys.argv) < 7:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    area, wallset, x, y = (int(v, 0) for v in sys.argv[3:7])
    rest = [a for a in sys.argv[7:] if not a.startswith("--")]
    map_area = int(rest[0], 0) if rest else None
    facing = int(rest[1], 0) if len(rest) > 1 else 0

    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    ids = [b[0] for b in blocks]
    if area not in ids:
        sys.exit(f"area 0x{area:02X} not present")

    marker = "--marker" in sys.argv
    intro = "--intro" in sys.argv
    code = build(area, wallset, x, y, map_area, facing, marker, intro)
    print(f"boot stub: {len(code)} bytes, entering area 0x{area:02X} "
          f"at ({x},{y}) with wall set {wallset}, "
          f"map area 0x{(area if map_area is None else map_area):02X}, "
          f"facing {facing}")

    # Verify the stub reads back as the instructions it was meant to be.
    table = G.load_opcodes()
    found = G.disassemble(code, table)

    claimed = sum(i.size for i in found.values())
    if claimed != len(code):
        sys.exit(f"stub does not disassemble cleanly: {claimed} of {len(code)} bytes")
    for off in sorted(found):
        print(f"    {off:04X}: {found[off].render()}")

    if intro:
        text, before, after = _intro_pool()
        print(f"  briefing: {len(before)} screens, kit of {len(STARTING_KIT)} "
              f"items and {STARTING_CREDITS} credits, then {len(after)} "
              f"arrival screen(s); {len(text)} bytes of text")
    else:
        text = b"\0" + MARKER + b"\0" if marker else b"\0"
    for entry in ENTRIES:
        if entry not in ids or entry == area:
            continue
        slot = ids.index(entry)
        print(f"  area 0x{entry:02X}: {len(blocks[slot][1])} -> {len(code)} bytes")
        blocks[slot] = (entry, code, text)
    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(expand.read_geo_stream(rom))
    out = builder.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

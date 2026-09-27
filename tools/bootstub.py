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

# X is 0x9AF7 and Y is 0x9AF6, not the other way round.
#
# The square lookup at 0x14CDC computes `d4 * 16 + d3`, and the caller loads
# d3 from 0x9AF7 and d4 from 0x9AF6. Both games store their maps row major:
# Countdown's own maps are 100% wall-consistent read as y*16+x and as low as
# 36% read as x*16+y. So d4 is Y and d3 is X, and the addresses are the
# reverse of what this file used to say.
#
# Read that way the delta table at 0x146E0 gives dx/dy of (0,-1), (+1,0),
# (0,+1), (-1,0) -- N, E, S, W, the same order DOS uses. No facing rotation,
# no flip, no transpose; the coordinates were simply crossed.
#
# Confirmed against play: at DOS (0,7) the south wall is 1 and the player
# saw a solid wall; one square east at (1,7) it is 13 and they saw a door.
DUNGEON_X, DUNGEON_Y, DUNGEON_DIR = 0x9AF7, 0x9AF6, 0x9AFA

# What inject_area.py builds its flag map from. See the note in main().
STOCK_ROM = Path(__file__).resolve().parent.parent / "roms/countdown.gen"

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

# And the man who approaches. In the DOS game he speaks the instant you
# arrive; here the stub prints the arrival line and hands over, so block 17's
# copy of the scene waits behind a step and the player is just left standing
# on the dock.
#
# This is block 17's own scene, lifted from 0x081A:
#
#     0081A  PICTURE     86
#     0081D  OR          4, [0x4C2F], [0x4C2F]    ; remember he has spoken
#     00826  PRINT_CLEAR "'WELCOME TO CALORIS...'"
#     008B4  PICTURE2    0, 255                   ; clear the window
#
# The flag matters: without it block 17 plays the scene again on the first
# step. DOS 0x4C2F is Genesis 0x9859, so the same bit can be set here, and
# OR rather than a plain write because the other bits of that byte are in
# use elsewhere in the block.
CHANCELLOR_PICTURE = 86
# The story flags the real opening sets, as DOS addresses. They are resolved
# through flagmap at build time rather than written here as Genesis numbers:
# this file used to carry CHANCELLOR_FLAG = 0x9859 as a literal, and 0x9859 is
# DOS 0x4C62 -- a flag belonging to blocks 34 and 36. The chancellor's real
# marker is DOS 0x4C2F bit 2, which is Genesis 0x9867. Marking the wrong byte
# is why De Sade greeted the party on arrival and then greeted them again the
# first time they stepped back onto the start square.
CHANCELLOR_FLAG_DOS, CHANCELLOR_BIT = 0x4C2F, 4

# Block 19's opening -- Buck's briefing, the kit, the walk out onto the dock --
# is reproduced in this stub rather than jumped into, so none of the state that
# opening sets gets set. DOS 0x4C30 is the one that matters: block 19 opens
# with `COMPARE [0x4C30], 0 / IF_EQUALS / GOTO <the opening>`, so with it clear
# every later `NEW_ECL 19` replays the whole briefing. That is what made LAUNCH
# at the port loop back to Buck and the treasure instead of reaching the hub.
OPENING_DONE_DOS = 0x4C30
CHANCELLOR = ("'WELCOME TO CALORIS. I AM LORD BERKELEY'S CHANCELLOR, ALPHONSE "
              "DE SADE. LORD BERKELEY SENDS HIS GREETINGS. THE CORONATION "
              "WILL BEGIN SHORTLY.' HE TURNS HIS BACK AND QUICKLY MOVES AWAY.")

STARTING_CREDITS = 8000
STARTING_KIT = [22, 22, 22, 22, 23, 23, 33, 33, 33, 8,
                8, 15, 6, 6, 6, 18, 10, 10, 35, 35]

INTRO_MUSIC = 0x30

# The orbit line plays over a full-width picture rather than the dock.
#
# VIEW's mode picks the layout and any id at or above 0x70 draws full width:
#
#     0851E: cmp.w  #$70, d3
#     08522: bcc.b  $8556        ; -> the big-picture loader
#     08550: bsr.w  $b7b4        ; otherwise the portrait window
#
# Countdown uses `VIEW 1, <big picture>` exactly six times, once each for
# ids 0x70, 0x73, 0x74, 0x75, 0x77 and 0x78 -- its cutscenes. 0x71 is
# Matrix Cubed's own BIGPIC1/113, a ship among asteroids, which is a better
# backdrop for "you ease into orbit" than standing on the coronation dock
# several scenes early.
#
# It reverts to VIEW 0 for Buck, so the establishing shot gives way to the
# ordinary screen with him talking in the window.
BRIEFING_VIEW_MODE, BRIEFING_BIGPIC = 0x01, 0x79

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
    for k, chunk in enumerate(transpile._split(CHANCELLOR)):
        after.append((CHANCELLOR_PICTURE if k == 0 else None, len(pool)))
        pool += chunk.encode("ascii", "replace") + b"\0"
    return bytes(pool), before, after


def build(area, wallset, x, y, map_area=None, facing=0, marker=False,
          intro=False, flags=None):
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
    # Load the geometry BEFORE the briefing, but hold NEWREGION back.
    #
    # The briefing used to run with no map loaded at all, so the dungeon
    # panel showed whatever happened to be left in it -- a corridor floating
    # over a starfield, which is nothing to do with the coronation dock.
    # LOADFILES and LOADPIECES put real geometry behind the text; NEWREGION
    # is what hands control to the area, so it stays at the end. That split
    # is why an earlier attempt to move the whole block after the setup
    # played nothing: everything queued after NEWREGION never runs.
    out += bytes([op["LOADFILES"]]) + _imm(area if map_area is None else map_area) \
        + _imm(0x7F) + _imm(0xFF)
    out += bytes([op["LOADPIECES"]]) + _imm(wallset)
    out += bytes([op["SAVE"]]) + _imm(y) + _mem(DUNGEON_Y)
    out += bytes([op["SAVE"]]) + _imm(x) + _mem(DUNGEON_X)
    out += bytes([op["SAVE"]]) + _imm(facing) + _mem(DUNGEON_DIR)

    # VIEW establishes the screen. Without it the briefing painted over
    # whatever was already there -- the team-select screen, empty character
    # slots showing through, nowhere for PICTURE to draw.
    #
    # Every VIEW in Countdown's own scripts passes id 0xFF, meaning "no big
    # picture": the opcode selects a display MODE rather than an image.
    # Area 0x10 shows the exact shape this needs --
    #
    #     VIEW        0x0, 0xFF     ; the ordinary game screen
    #     PICTURE     0x48          ; portrait into the window
    #     PRINTCLEAR  str[0x0000]   ; text into the box beneath
    VIEW_GAME_SCREEN, VIEW_NO_PICTURE = 0x00, 0xFF

    if intro:
        _, before, after = _intro_pool()

        def screen(pic, at):
            if pic is not None:
                out.extend(bytes([op["PICTURE"]]) + _imm(pic))
            out.extend(bytes([op["PRINTCLEAR"]]) + bytes([0x80])
                       + struct.pack("<H", at))
            out.extend(bytes([op["CONTINUE"]]))

        out += bytes([op["VIEW"]]) + _imm(BRIEFING_VIEW_MODE) + _imm(BRIEFING_BIGPIC)
        out += bytes([op["SOUND"]]) + _imm(INTRO_MUSIC)
        for k, (pic, at) in enumerate(before):
            if pic is not None and k:
                # Buck: back to the ordinary screen, portrait in the window.
                out += bytes([op["VIEW"]]) + _imm(VIEW_GAME_SCREEN) \
                    + _imm(VIEW_NO_PICTURE)
            screen(None if k == 0 else pic, at)
        out += bytes([op["CLEARMONSTERS"]])
        out += bytes([op["TREASURE"]]) + _imm(STARTING_CREDITS) \
            + _imm(len(STARTING_KIT)) + b"".join(_imm(i) for i in STARTING_KIT)
        out += bytes([op["COMBAT"]])
        for pic, at in after:
            screen(pic, at)
        # Mark him as having spoken, so block 17 does not replay the scene.
        chancellor = flags[CHANCELLOR_FLAG_DOS]
        out += bytes([op["OR"]]) + _imm(CHANCELLOR_BIT) \
            + _mem(chancellor) + _mem(chancellor)
        # ...and mark the opening itself as done, so block 19 goes to the hub
        # instead of replaying the briefing every time the ship launches.
        out += bytes([op["SAVE"]]) + _imm(1) + _mem(flags[OPENING_DONE_DOS])
        # He turns his back and moves away, so take his face out of the
        # window. VIEW 0, 0xFF only restores the layout -- it was leaving him
        # sitting there until the player took a step. The clear is on the
        # picture path, which tests the id for a sign bit:
        #
        #     04DFA: move.b $b525.w, d0
        #     04DFE: bpl.b  $4e04        ; negative -> clear instead of load
        out += bytes([op["VIEW"]]) + _imm(VIEW_GAME_SCREEN) + _imm(VIEW_NO_PICTURE)
        out += bytes([op["PICTURE"]]) + _imm(0xFF)

    out += bytes([op["NEWECL"]]) + _imm(area)
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
    # The flag map MUST be computed from the stock cartridge, not from the
    # ROM being patched. flagmap.build scans the engine's own code for
    # addresses it treats as spoken for, so it returns a different allocation
    # for a half-built ROM than for the stock one -- and inject_area.py, which
    # transpiled every script, built its map from the stock cartridge. Reading
    # it off `rom` here put the chancellor's bit at 0x9731 instead of 0x9867:
    # a stub that marks an address no script ever reads.
    import flagmap
    flags = flagmap.build(Path(STOCK_ROM).read_bytes())
    code = build(area, wallset, x, y, map_area, facing, marker, intro, flags)
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

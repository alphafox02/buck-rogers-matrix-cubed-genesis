#!/usr/bin/env python3
"""
Build the playable ROM.

The transplant list had been living in shell history, which is no way to
keep a build. This is the whole recipe.

    python3 tools/build.py [out.gen]

Area ids follow the DOS block numbers, in hex -- a convention the exit
graph confirms, since every NEWECL target across all 33 blocks resolves to
a block that exists under it.

Three blocks need spelling out:

  block 1  -> area 0x00   Countdown's boot block and Matrix Cubed's block 1
                          are direct counterparts: both open with "DO YOU
                          WANT TO START FROM SCRATCH OR USE THE JUMPER?".
                          Replacing it outright is what makes the game
                          start in Matrix Cubed rather than falling into
                          Countdown's travel menu.
  block 2  -> area 0x02   SSI's combat test room, which block 1 exits to.
  maps 1, 51, 52          geometry with no script of its own. LOADFILES
                          names a map id, and areas 0x31 and 0x32 load
                          0x34 and 0x33 as sub-levels of their region.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import dax
import soundmap

# Where the player starts. Area 0x18 is block 24, and block 24 is the
# game's actual opening -- not a room but the prologue cutscene, which is
# what seeds the party with the story NPCs:
#
#     00040  LOAD_AREA_MAP   64, 127, 255
#     00047  LOAD_AREA_DECO  7, 127, 127
#     0004E  WRITE_MEM       13, [0xC04B]   ; party x
#     00054  WRITE_MEM       8,  [0xC04C]   ; party y
#     0005A  WRITE_MEM       3,  [0xC04D]   ; facing
#     00060  SOUND_EVENT     129            ; music cue 0x81
#     00068  NPC_ADD         55, 100        ; Buck Rogers and company
#     00077  PRINT_CLEAR     "UNDER THE LEADERSHIP OF BUCK ROGERS, YOUR TEAM
#                             MUST NOW EMBARK ON A MISSION OF SALVATION..."
#
# It was area 0x11 before, which is block 17 -- the Mercury coronation. That
# is a real scene and it plays, but it is not the beginning: the party
# arrives there already knowing who Buck Rogers is, because the prologue
# that introduces him was never run.
#
# Block 24 has no map of its own (GEO1 has no map 24); it loads map 64,
# which this build already installs at geo area 0x40. Wall set and position
# match what the script sets for itself.
START = ("0x18", "7", "13", "8")

STOCK = REPO / "roms/countdown.gen"
DEFAULT_OUT = REPO / "roms/matrix_play.gen"

# Transplanted as <area>:<block>[:<map>]; a block of `-` is map-only.
MAP_ONLY = ["0x01:-:1", "0x33:-:51", "0x34:-:52"]

# PICTURE ids Matrix Cubed's scripts name that have recovered artwork. They
# go into the real ECL picture directory at 0x51326/0x51360, at the full
# 88x88 the DOS originals use, with the palette embedded in each image.
# Portraits, as picture id -> source. Most come from PIC1, whose 46 blocks
# all decoded; three live in other archives the same decoder recovered, and
# every one of them is 88x88, the size this container wants.
PORTRAITS = {
    0x20: "PIC1/032",   0x25: "SPRIT1/037", 0x3C: "PIC1/060",
    0x40: "SPRIT1/064", 0x50: "PIC1/080",   0x51: "PIC1/081",
    0x52: "PIC1/082",   0x54: "PIC1/084",   0x55: "PIC1/085",
    0x56: "PIC1/086",   0x5B: "PIC1/091",   0x5C: "PIC8/092",
    0x5D: "PIC1/093",   0x5E: "PIC1/094",   0x5F: "PIC1/095",
    0x61: "PIC1/097",
}

# Music. Every slot the game can reach with a Matrix Cubed song.
# slot 2 is the intro (SOUND 0x2E) and slot 10 the menu and team setup
# (SOUND 0x36). Replacing all fourteen was tried and crashed the machine
# about two runs in three, while one slot and two slots both measure clean,
# so the rest wait until the reason is understood rather than being pushed
# in because they fit.
#
# BUCKA, BUCKB and BUCKC hold the SAME seven songs in three arrangements for
# different DOS sound cards -- their tick lengths match to within two -- and
# BUCKA is the richest.
# slot 2 is the intro (SOUND 0x2E) and slot 10 the menu (SOUND 0x36); the
# rest are the slots tools/soundmap.py sends Matrix Cubed's six music cues
# to, so every cue in the scripts now reaches a Matrix Cubed song.
MUSIC = {2: ("BUCKA.XMI", 0)}
MUSIC.update({slot: ("BUCKA.XMI", song)
              for slot, song in sorted(soundmap.SONGS.items())})

# VIEW big pictures, 288x120. The ids ARE the DOS BIGPIC1 numbers: 0x70 is
# 112 in decimal, which is what the archive calls it.
BIGPIC_IDS = [112, 115, 116, 117]

# NOT INJECTED. The table at 0xF14F2 these ids index turned out to be the
# engine's ITEM AND UI icon table, not the ECL PICTURE directory -- its two
# consumers are a 0xFF-terminated batch loader at 0x0A794 and an item lookup
# at 0x10AC4, and the ECL PICTURE opcode is neither. It was mistaken for the
# picture directory because its 110 entries happen to match the PICTURE id
# range, which was a coincidence and was never checked. Writing portraits
# into it replaced the inventory and equipment icons, which is what a play
# session saw.
#
# Kept for when the real picture path is found.
PICTURES = """
0x02:PIC1/002 0x1D:PIC1/029 0x1E:PIC1/030 0x1F:PIC1/031 0x20:PIC1/032
0x37:PIC1/055 0x38:PIC1/056 0x39:PIC1/057 0x3C:PIC1/060 0x50:PIC1/080
0x51:PIC1/081 0x54:PIC1/084 0x55:PIC1/085 0x56:PIC1/086 0x59:PIC1/089
0x5B:PIC1/091 0x5D:PIC1/093 0x5E:PIC1/094 0x5F:PIC1/095 0x60:PIC1/096
0x61:PIC1/097 0x62:PIC1/098 0x65:PIC1/101 0x66:PIC1/102 0x67:PIC1/103
0x68:PIC1/104 0x6A:PIC1/106 0x6B:PIC1/107_5
""".split()


def specs():
    blocks = dax.load(REPO / "dos_game/matrix/ECL1.DAX")
    maps = dax.load(REPO / "dos_game/matrix/GEO1.DAX")
    out = []
    for b in sorted(blocks):
        if b == 1:
            # Block 1's script goes to area 0x00, but its map does not: the
            # block does LOADFILES 1, which names map id 1, so the geometry
            # belongs at geo area 0x01 and is listed in MAP_ONLY. Attaching
            # it here as well would duplicate it and spend one of the
            # engine's 32 geo slots for nothing.
            out.append("0x00:1")
            continue
        out.append(f"0x{b:02X}:{b}" + (f":{b}" if b in maps else ""))
    return out + MAP_ONLY


def main():
    # --no-art stops before the picture work, to tell a transplant problem
    # apart from an art one.
    art = "--no-art" not in sys.argv
    bigpics = "--no-bigpic" not in sys.argv
    portraits = "--no-portrait" not in sys.argv
    music = "--no-music" not in sys.argv
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(argv[0]) if argv else DEFAULT_OUT

    # Build into a scratch file and rename it into place at the very end.
    #
    # Every stage reads and writes the same ROM, so building straight into
    # `out` means that for most of a build the file on disk is a half
    # converted ROM -- after the areas go in but before the title art, it
    # still carries Countdown's intro. Loading it at that moment shows the
    # old intro, or worse a torn file, and looks exactly like a regression.
    # `Path.replace` is atomic within a filesystem, so the emulator only
    # ever sees a finished ROM or the previous one.
    work = out.with_name(out.name + ".building")

    def step(tool, *args):
        rc = subprocess.call([sys.executable, str(REPO / "tools" / tool),
                              str(work), str(work), *args])
        if rc:
            work.unlink(missing_ok=True)
            raise SystemExit(rc)

    rc = subprocess.call([sys.executable, str(REPO / "tools/inject_area.py"),
                          str(STOCK), str(work)] + specs())
    if rc:
        work.unlink(missing_ok=True)
        raise SystemExit(rc)

    # Both games' area 0x00 is a developer warp menu rather than a boot
    # block, so replace it with a stub that just enters the game.
    step("bootstub.py", *START)
    # A resource Countdown does not carry must not be able to end the run.
    step("softfail.py")
    step("retitle.py")

    # Matrix Cubed's own portraits, into the slots the directory ALREADY has.
    #
    # The directory is deliberately NOT expanded. Adding ids looked free and
    # is not: the loader at 0x0B7D2 walks the id list, and on running off the
    # end it calls 0x082EC to pick a sensible default and retries. Every id
    # Matrix Cubed names that Countdown lacks was taking that path safely.
    # Adding those ids turned each miss into a hit on a placeholder -- and
    # the placeholder is the largest picture in the ROM, six frames and 12 KB
    # -- which overflowed depending on heap state. It showed up as a crash on
    # "restore game" that happened perhaps one run in three.
    #
    # Replacing what is already there has no such effect: same id, same
    # budget, art that fits.
    if art and portraits:
        step("inject_portrait.py",
             *[f"0x{k:02X}:{v}" for k, v in sorted(PORTRAITS.items())])
    if art and bigpics:
        # The intro screens are named by lea operands rather than a
        # directory, so replacing them needs no table to grow.
        step("inject_title.py")
        step("trim_intro.py")
        step("inject_portrait.py", "--bigpic",
             *[f"0x{p:02X}:BIGPIC1/{p:03d}" for p in BIGPIC_IDS])
    if music:
        step("inject_music.py",
             *[f"{slot}:{f}:{song}" for slot, (f, song) in sorted(MUSIC.items())])

    work.replace(out)
    print(f"published {out}")


if __name__ == "__main__":
    main()

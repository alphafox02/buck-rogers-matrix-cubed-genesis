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
import monstermap
import soundmap

# Where the player starts.
#
# Area 0x11 is block 17, the coronation room. It is where the DOS game puts
# you after its opening, and it is the configuration that plays stably.
#
# Block 19 is the opening proper -- the Mercury briefing, matching the DOS
# game beat for beat -- and booting into it was tried and reverted. It never
# does NEWECL: it IS the script for that stretch, and its movement hook
# (GOTO 0x87CC) is the ship, so with the stub dropping the player into a
# walkable map 17 straight away, the first step east goes to space and the
# jury-rig check. Block 19 expects to run its cutscene before anyone can
# move. Entering it properly means the stub loading no map and letting the
# script place the player, which is a change to make deliberately and test,
# not to bolt on.
#
# The map is named separately because a block's map need not share its id,
# and the facing needs translating rather than copying: the Genesis delta
# table at 0x146E0 gives dy/dx of (0,-1), (+1,0), (0,+1), (-1,0) for
# directions 0..3, and play confirms y increases northward, so the Genesis
# order is W, N, E, S against the DOS N, E, S, W -- genesis = (dos + 1) & 3.
# Block 17 is entered facing east, which is Genesis 2.
#
# Wall set 4 is Genesis set 1, what tools/wallmap.py maps block 17's
# LOAD_AREA_DECO 5 onto. Passing the DOS 5 straight through put it on set 0.
# The DOS start, 0,2 facing east, which is what its status line reads here.
# Maps are NOT flipped -- see tools/inject_area.flip_map for why that was
# tried and backed out -- so the coordinate is used as it stands.
#
# 3 was tried, on the reasoning that the Genesis draws the room
# three-quarter overhead rather than first person so the DOS number need
# not be the right one. It showed the player standing in space, and the
# reason is geometry rather than art: the delta table has y increasing
# northward, so south from y=2 looks off the bottom edge of a 16x16 map
# and there is nothing out there to draw but the backdrop.
# Figure ids whose artwork is drawn at 24x48 or 48x24 rather than 24x24.
# From the size class in byte 7 of each figure record at 0x9A14.
LARGE_FIGURES = (0x04, 0x05, 0x06, 0x0B, 0x10, 0x17, 0x18, 0x23, 0x28)

START = ("0x11", "4", "0", "2", "0x11", "1")

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
    # Named by the scripts, already in the directory, and DOS has the art --
    # they were simply never listed. Surveying every id the scripts call
    # against what we replace turned these up: 47 are named, and these were
    # three of the ten still drawing Countdown's pictures. The other seven
    # (0x79, 0x3E, 0x46-0x49) have no DOS source at all, so they stay.
    0x2A: "PIC1/042",   0x59: "PIC1/089",   0x6F: "PIC1/111",
}

# Ids the stock directory does NOT hold, added by tools/expand_pictures.py.
# These are what the opening scenes name -- Buck Rogers is 57, Mercury 101 --
# and until now every one of them missed the directory and drew whatever the
# engine's fallback picked, which is the wrong art in the portrait window.
#
# This list and the expansion list are the same list on purpose. An added id
# with no art inherits the directory's first entry, the largest picture in
# the cartridge, and that is what crashed the earlier attempt.
ADDED_PORTRAITS = {
    0x39: "PIC1/057",   # Buck Rogers, the briefing
    0x60: "PIC1/096",   0x62: "PIC1/098",
    0x65: "PIC1/101",   # Mercury from orbit
    0x66: "PIC1/102",   0x67: "PIC1/103",
    0x68: "PIC1/104",   0x6B: "PIC1/107_5",
    # The rest of what the scripts name and the cartridge lacks, ordered by
    # how often they are used: 0x1D is called 41 times and 0x37 21 times, so
    # these are not corner cases -- they are faces the player meets over and
    # over. Ids below 0x20 are fine; the loader searches the list linearly
    # and does not care what range the stock ids happen to occupy.
    0x02: "PIC1/002",   0x04: "PIC1/004",   0x1D: "PIC1/029",
    0x1E: "PIC1/030",   0x1F: "PIC1/031",   0x37: "PIC1/055",
    0x63: "PIC1/099",
    # The last three the scripts name that the archives hold. With these the
    # only PICTURE ids left substituted are 0xFF, which means "no picture".
    0x17: "PIC1/023",   0x38: "PIC1/056",   0x6A: "PIC1/106",
    # NOT 0x6F. It is the one opening-area picture already in the directory,
    # so it looked like a free win, but no Countdown script references it --
    # meaning whatever loads it is engine UI, and the team-selection screen
    # went odd the moment it was replaced. One picture is not worth breaking
    # a screen the player has to pass through.
    #
    # The rest of what block 19 and block 17 name -- 57, 96, 98, 101, 102,
    # 103, 104, 107 -- are ids Countdown does not carry at all, so they miss
    # the directory and the loader substitutes a default. That is the wrong
    # art in the portrait window, and fixing it needs the directory
    # expanded rather than a slot replaced.
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
# VIEW big pictures. 113 and 114 are NOT in the stock directory -- the
# scripts name 113 six times -- so the VIEW tables get the same expansion
# the portrait ones do, and every id here is injected straight after.
BIGPIC_IDS = [112, 113, 114, 115, 116, 117]

# 113 and 114 are added and injected. 0x79 is added and deliberately NOT
# injected: expand_pictures gives every new id ptrs[0], and at that point in
# the build ptrs[0] is still Countdown's own 0x70 -- the space scene with
# human ships against a station gantry. Leaving it uninjected is how the
# briefing keeps that picture after Matrix Cubed's art takes over slot 0x70.
#
# This is the one exception to "added ids must be injected". That rule exists
# because an uninjected id inherits the biggest blob in the cartridge, which
# overflowed; here the inherited picture is an ordinary 507-tile VIEW image,
# the same size as everything else in this directory, and the VIEW tables
# have no metadata to get out of step.
BIGPIC_ADDED = [113, 114, 0x79]

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
    # Say plainly whether the two games are present before doing anything.
    import checkinputs
    missing, _ = checkinputs.check()
    if missing:
        raise SystemExit(
            "\nNothing to build from. This repository contains no game data:\n"
            "  roms/countdown.gen    a Countdown to Doomsday cartridge dump\n"
            "  dos_game/matrix/      a Matrix Cubed DOS installation\n"
            "Run tools/checkinputs.py for the full list.")

    # --no-art stops before the picture work, to tell a transplant problem
    # apart from an art one.
    art = "--no-art" not in sys.argv
    bigpics = "--no-bigpic" not in sys.argv
    portraits = "--no-portrait" not in sys.argv
    music = "--no-music" not in sys.argv
    # Back ON. Adding the creatures corrupted the combat map -- blocks of
    # noise on the floor during a fight -- and the cause was two address
    # collisions, not VRAM as first suspected:
    #
    #   the figure directory sat at 0x1B1800, INSIDE the enlarged monster
    #   stream at 0x1B1000, so add_creatures wrote the stream over the
    #   figure records and combat drew tiles out of compressed monster data
    #
    #   and add_creatures wrote that stream back IN PLACE at 0x09E77C, where
    #   stock packs into 2809 bytes and real data follows, so about 1290
    #   bytes of it were overrun
    #
    # Both are fixed -- the directory moved to 0x1B4000 and the stream
    # relocates like everything else -- and the same encounter now draws
    # clean with the creatures on.
    creatures = "--no-creatures" not in sys.argv
    expand = "--no-expand" not in sys.argv
    party = "--no-party" not in sys.argv
    demo = "--no-demo" not in sys.argv
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

    # Every step's output is kept as well as printed, so romlayout.py can
    # read back where each injector wrote and fail the build if two of them
    # overlap. That has happened three times and never announced itself.
    transcript = []

    def run(cmd):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        transcript.append(proc.stdout)
        if proc.returncode:
            work.unlink(missing_ok=True)
            raise SystemExit(proc.returncode)

    def step(tool, *args):
        run([sys.executable, str(REPO / "tools" / tool),
             str(work), str(work), *args])

    run([sys.executable, str(REPO / "tools/inject_area.py"),
         str(STOCK), str(work)] + specs())

    # Both games' area 0x00 is a developer warp menu rather than a boot
    # block, so replace it with a stub that just enters the game.
    step("bootstub.py", *START, "--intro")
    # A resource Countdown does not carry must not be able to end the run.
    step("softfail.py")
    # 0x9AF8 -- the wall the party faces, which 80 script sites read --
    # was only recomputed when the party MOVED, so every gate on it was
    # answered one action late. See tools/wallvalue.py.
    step("wallvalue.py")
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
        shown = dict(PORTRAITS)
        if expand:
            # The directory grows and the new ids are injected in the same
            # breath -- see the note on ADDED_PORTRAITS.
            step("expand_pictures.py", *[f"0x{k:02X}" for k in sorted(ADDED_PORTRAITS)])
            shown.update(ADDED_PORTRAITS)
        step("inject_portrait.py",
             *[f"0x{k:02X}:{v}" for k, v in sorted(shown.items())])
    if art and bigpics:
        # The intro screens are named by lea operands rather than a
        # directory, so replacing them needs no table to grow.
        step("inject_title.py")
        step("trim_intro.py")
        # DOS's order, which the port had lost: SSI presents, then the Buck
        # Rogers logo with the copyright lines UNDER it rather than stranded
        # on a screen of their own, then the credits. The third screen comes
        # out of the code trim_intro.py just made unreachable.
        step("introfix.py")
        if expand:
            step("expand_pictures.py", "--bigpic",
                 *[f"0x{p:02X}" for p in BIGPIC_ADDED])
        step("inject_portrait.py", "--bigpic",
             *[f"0x{p:02X}:BIGPIC1/{p:03d}" for p in BIGPIC_IDS])
    # Room for both rosters. Harmless on its own -- it widens a stack buffer
    # and nothing else -- and it is what any creature added later needs.
    # Matrix Cubed's courtesy console, which the DOS map puts on the dock
    # wall and Countdown's wall set has no piece for. Hand drawn at native
    # resolution: the downscaled DOS pixels were tried and are worse.
    if art:
        step("injectconsole.py", "drawn", "--nopal")
    # Room for both rosters. Harmless on its own -- it widens a stack buffer
    # and nothing else -- and it is what any creature added later needs.
    step("monstercap.py")
    # A 48x48 creature size. Stock Countdown draws 24x24, 24x48 and 48x24.
    #
    # NOT bigfigures.py: that patched the figure record's size class, which
    # probing showed the combat board ignores -- figure class 0 with monster
    # size 2 draws tall, figure class 2 with monster size 1 draws small. The
    # board reads the MONSTER record's byte 0x23, and bigcreature.py extends
    # the three routines that were measured taking that path in a live fight.
    step("bigcreature.py")
    # Matrix Cubed's own creatures, each with a slot, a name and a figure of
    # its own. The figure directory grows first: monster id and figure id are
    # the same number, and a monster with no figure takes the miss path.
    if creatures:
        step("expand_figures.py",
         *[f"0x{nid:02X}:0x{src:02X}"
               for nid, (_name, src) in sorted(monstermap.NEW_CREATURES.items())])
        step("add_creatures.py")
        # Real Matrix Cubed artwork for the creatures just added, at the size
        # each one is drawn in DOS. --auto reads the DOS monster records to
        # find which CPIC1 block belongs to which creature rather than being
        # told; see inject_creature.py.
        step("inject_creature.py", "--auto")
        # NOT APPLIED. Three added creatures clone a large donor and inherit
        # its size class (ASSAULT ROBOT and COMBAT ROBOT from 48x24 donors,
        # COYODORG from a 24x48 one), and substituting a large figure into
        # the opening encounter draws a 24x24 crop -- half a creature. So
        # tools/rescale_figure.py redraws them at 24x24, and running it here
        # would make them whole.
        #
        # It is off because the premise is not proven. Countdown ships nine
        # large figures whose frames carry shadows at the bottom, art that
        # only makes sense drawn whole, and the engine has machinery for
        # exactly that: 0xC358 lifts a class 2 figure 24px so it stands on
        # the floor, and the allocator reserves two slots so the creature
        # beside it is not overlapped. None of that exists unless tall
        # creatures are drawn tall somewhere.
        #
        # The substitution tests that showed truncation put a figure record
        # under a monster the engine spawned as something else, and three
        # follow-ups failed to reproduce a tall draw either way: giving the
        # one combatant the engine tracks ($B018, figure 0x1E) a class 2
        # record changed nothing on screen because it is not drawn at all,
        # and forcing the monster loader to id 0x04 changed the encounter
        # without changing the artwork. So the figures on the board come
        # from a path still not identified, and shrinking three creatures on
        # the strength of a test that does not model a real spawn would trade
        # a maybe-bug for a definite one.
        #
        # Turn this on once a large creature has been seen truncated in
        # ordinary play.
    else:
        step("rename_monsters.py")
    # The pregenerated team at level 8 with perception. Countdown's own team
    # is a level 1 party built for Countdown's first encounter; Matrix Cubed
    # opens on robots that expect a party carried over from it.
    if party:
        step("boostparty.py", "--veteran")
    # DOS block 24, the attract-mode demo, is already transplanted as area
    # 0x18 and nothing has ever called it. This points the idle timeout at it.
    if demo:
        step("demomode.py")
    if music:
        step("inject_music.py",
             *[f"{slot}:{f}:{song}" for slot, (f, song) in sorted(MUSIC.items())])

    import romlayout
    if romlayout.main_from_text("".join(transcript)):
        work.unlink(missing_ok=True)
        raise SystemExit("ROM layout check failed: two injectors overlap")

    work.replace(out)
    print(f"published {out}")


if __name__ == "__main__":
    main()

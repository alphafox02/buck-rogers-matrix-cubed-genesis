# Buck Rogers: Matrix Cubed — Genesis

Transplanting the DOS scenario *Buck Rogers: Matrix Cubed* (1992) into the
Sega Genesis engine of *Buck Rogers: Countdown to Doomsday* (1991), so the
second game can be played on the console the first one never reached.

Both games run SSI's Gold Box engine. The Genesis one is a port of it, and
the two are close enough that a scenario written for one can be made to run
on the other — but only after every id that crosses between them is
translated, because the engine rarely errors on a wrong id. It indexes off
the end of a table and carries on.

## This repository contains no game data

It is tooling and reverse-engineering notes. Nothing from either game is
committed here, and `.gitignore` refuses `roms/`, `dos_game/` and every
`.gen .DAX .XMI .OVR .EXE .ADV .BNK .CAT`.

**You supply two things, both of which you must already own:**

```
roms/countdown.gen     the Genesis Countdown to Doomsday cartridge, 1 MB
                       -- this is the ENGINE the port runs on

dos_game/matrix/       a Matrix Cubed DOS installation, 51 files
                       -- this is the CONTENT: art, maps, scripts, music,
                          monster and item tables
```

Both are needed. Matrix Cubed is a DOS program and contains no Genesis code
at all; Countdown supplies the 68000 engine, the tile renderer and the sound
driver, and the tools here translate one into the other. Nine of those files
are read at build time and each is checked by SHA-1 first:

```
python3 tools/checkinputs.py
```

It names exactly what is wanted and whether yours are the dumps every offset
in `tools/` was measured against. A different revision is a warning, not a
refusal — it may well work.

## Reproducible

The build is a pure function of those inputs. Delete the output, run it
twice, and the two ROMs are byte-identical; nothing is layered on anything
previously extracted.

## Building

```
python3 tools/checkinputs.py                  # are the inputs there and right?
python3 tools/build.py                        # -> roms/matrix_play.gen
python3 tools/boottest.py roms/matrix_play.gen
```

`tools/build.py` is the whole recipe: it transplants the areas, replaces the
boot block, injects artwork, converts the music, maps the ids and repairs
the cartridge checksum. Flags let you bisect — `--no-art`, `--no-music`,
`--no-expand`, `--no-creatures`, `--no-bigpic`, `--no-portrait`.

## What works

- **All 33 areas** transplanted, all 78 area transitions intact, 29 of 33
  reachable from the opening (the four that are not are SSI's developer
  menu, its combat test room, an empty stub and the attract demo)
- **4,536 of 4,552 text lines** survive, re-paginated for a window four
  lines shorter than the DOS one
- **The opening plays**: space cutscene, Buck Rogers briefing, the starting
  kit of 8000 credits and 20 items, the dock, the chancellor
- **Music** converted from XMI to the Z80 driver's own sequence format
- **Combat runs** — encounters fire, initiative resolves, experience is
  awarded
- **Matrix Cubed's own 36 creatures** have roster slots and names, with the
  engine's 64-monster ceiling raised to 128
- **27 of the 36 wear their own DOS artwork**, quantised to the sixteen
  colours the engine gives a combat figure and resolved automatically: a DOS
  monster record names its sprite at byte 185 and a creature's two poses are
  blocks `N` and `N+128` of `CPIC1`. The other nine name a block `CPIC1` does
  not have, and keep the Countdown figure they were substituted for, which
  was picked by role and is usually close -- SECURITY ROBOT keeps RAM H.S.
  ROBOT, LOWLANDER keeps LL. WARRIOR
- **A 48x48 creature size**, which the Genesis engine did not have. Stock
  Countdown draws 24x24, 24x48 and 48x24; Matrix Cubed has five creatures
  at 48x48, the Venus Dinosaur among them, and they now draw at full size
  standing on two grid squares by two

## What does not, yet

- Creatures animate between two poses only, because that is all a DOS block
  holds; a real walk cycle needs the frame grouping in `docs/art_todo.md`
- Some wall graphics are wrong, because a wall value selects a picture from
  the loaded wall set and the two games disagree about what each value looks
  like. Doors that Countdown would draw as solid are corrected; the rest are
  left alone
- Three instructions in SSI's developer block still do nothing

## Layout

```
docs/re_notes.md    the reverse engineering: formats, addresses, what was
                    measured and what is still a guess
docs/devlog.md      what happened, including what was wrong and why
tools/              65 programs. build.py is the entry point and the whole
                    recipe; about fifteen are build steps and the rest are
                    research instruments that never touch the output ROM
tests/              unit tests for the codecs
```

## Verifying

`tools/play.py` drives a build under a scriptable Genesis core: it presses
buttons, reads RAM and captures frames. It boots, loads the pregenerated
team, plays the opening and walks the dungeon, which is how the map and the
party's start square are checked without anyone watching. It cannot fight,
so it stalls at the first encounter.

`tools/boottest.py` is the cheap version: does the ROM boot, reach the menu,
and still carry its cartridge serial.

## Credit

*Countdown to Doomsday* and *Matrix Cubed* are SSI's, from TSR's Buck Rogers
setting. This project distributes neither. It is a conversion tool for
people who own both.

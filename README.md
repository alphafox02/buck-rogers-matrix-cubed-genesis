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

It is tooling and reverse-engineering notes. Everything it needs is read out
of copies of the two originals that you already own, and nothing from either
game is committed here. You supply:

```
roms/countdown.gen            a Countdown to Doomsday cartridge dump (1 MB)
dos_game/matrix/              a Matrix Cubed DOS installation
```

Run `python3 tools/checkinputs.py` to see exactly which files are wanted and
whether yours are the dumps every offset in `tools/` was measured against. A
different revision is a warning, not a refusal — it may well work.

## Building

```
python3 tools/checkinputs.py          # are the inputs there and right?
python3 tools/build.py roms/out.gen   # write the ROM
python3 tools/boottest.py roms/out.gen
```

`tools/build.py` is the whole recipe: it transplants the areas, replaces the
boot block, injects artwork, converts the music, maps the ids and repairs
the cartridge checksum. Flags let you bisect — `--no-art`, `--no-music`,
`--no-expand`, `--creatures`.

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

## What does not, yet

- Creature artwork is Countdown's, matched by role. Adding Matrix Cubed's 36
  own creatures corrupts the combat map, so it is off by default
  (`--creatures` builds it)
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
tools/              ~30 programs; build.py is the entry point
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

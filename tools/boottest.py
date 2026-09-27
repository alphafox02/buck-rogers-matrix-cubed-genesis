# SPDX-License-Identifier: MIT
"""
Check a built ROM actually boots, without a person watching it.

Every interactive bug on this project was found by someone playing and
sending a screenshot, and several builds were handed over broken because the
only automated check -- BlastEm's address log -- proves almost nothing. It
records each address once, not in execution order, so it cannot tell a boot
that reached the menu from one that died in the intro.

This runs the ROM under a scriptable Genesis core and looks at the screen:

    logos      the EA and Buck Rogers screens draw
    title      the Matrix Cubed card draws
    menu       the main menu draws, with its five icons

It does NOT play the game. Getting past the menu needs a character created,
and automating character creation and combat is a project of its own -- the
harness in tools/play.py can drive buttons and read RAM if that is ever
worth doing.

What this catches is the class of failure that wasted the most time: a ROM
that never gets as far as a person can see.

Usage:
    boottest.py [rom ...]
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

STAGES = (("logos", 6, 2000), ("title", 10, 8000), ("menu", 14, 15000))

# The cartridge serial must not move. An emulator's ROM database is keyed on
# it -- BlastEm prints "Product ID: T-50286" and then finds the entry -- and
# that same entry supplies the SRAM mapping. Changing it once made the game
# stop loading altogether, so retitle.py leaves it alone and this checks that
# it stayed left alone. The name fields are free to change; the lookup does
# not use them.
SERIAL = (0x180, 14)


def serial_ok(rom, stock=REPO / "roms/countdown.gen"):
    a, n = SERIAL
    want = Path(stock).read_bytes()[a:a + n]
    got = Path(rom).read_bytes()[a:a + n]
    if got != want:
        print(f"  {Path(rom).name}: SERIAL CHANGED, {got!r} not {want!r} -- "
              f"an emulator may refuse the ROM or lose its SRAM mapping")
        return False
    return True


def check(rom):
    ok_serial = serial_ok(rom)
    from play import Game
    g = Game(rom)
    g.run(420)
    seen = {}
    best = 0
    for k in range(26):
        best = max(best, g.lit())
        for name, at, want in STAGES:
            if k >= at and name not in seen and best >= want:
                seen[name] = best
        g.tap("C", hold=6, rest=45)
    ok = len(seen) == len(STAGES) and ok_serial
    print(f"  {Path(rom).name}: " + ", ".join(
        f"{n} {'ok' if n in seen else 'MISSING'}" for n, _, _ in STAGES)
        + f", serial {'ok' if ok_serial else 'CHANGED'}"
        + f"   (brightest frame {best} px)")
    return ok


if __name__ == "__main__":
    roms = sys.argv[1:] or [str(REPO / "roms/matrix_play.gen")]
    bad = 0
    for r in roms:
        try:
            if not check(r):
                bad += 1
        except Exception as e:
            print(f"  {Path(r).name}: FAILED to run -- {type(e).__name__}: {e}")
            bad += 1
    print("all boot" if not bad else f"{bad} of {len(roms)} did not boot")
    sys.exit(1 if bad else 0)

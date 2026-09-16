"""
Map Matrix Cubed's wall-set ids onto the ones the Genesis engine has.

`LOAD_AREA_DECO` becomes `LOADPIECES`, and the Genesis handler turns the
argument into a set index by dividing:

    03ADE  divu.w  #$3,d2        ; wallset index
    03AE2  move.b  d2,$9AFB.w

so the ten sets are addressed by the values Countdown's own scripts use --
1, 4, 7, 10, 13, 16, 19, 22, 25 and 28, one per set, all of the form 3k+1.

Passing DOS ids through unchanged was wrong in a way that is invisible until
you look at a wall. Integer division makes every id land on *some* set, so
nothing errors; but Matrix Cubed's ids collide and cluster:

    DOS 3 and 5   -> set 0        DOS 9 and 11  -> set 3
    DOS 15 and 17 -> set 5        sets 8 and 9 never reached at all

Matrix Cubed uses exactly ten distinct decos and the Genesis has exactly ten
sets, so they are matched in order. That the counts agree is a fact; that
the orders correspond is a guess, and the one to revisit first if an area's
walls look wrong. Each entry is easy to repoint on its own.
"""

# DOS LOAD_AREA_DECO id -> Genesis LOADPIECES argument
WALLS = {
     3:  1,     # -> set 0
     5:  4,     # -> set 1   the Mercury interiors, blocks 17/18/19/80
     7:  7,     # -> set 2
     9: 10,     # -> set 3
    11: 13,     # -> set 4
    13: 16,     # -> set 5
    15: 19,     # -> set 6
    17: 22,     # -> set 7
    19: 25,     # -> set 8
    22: 28,     # -> set 9
}

# What Countdown's own areas pass, for reference when repointing one.
GENESIS_SETS = (1, 4, 7, 10, 13, 16, 19, 22, 25, 28)


def translate(deco):
    """Return (genesis_argument, was_remapped)."""
    if deco in WALLS:
        return WALLS[deco], True
    # Anything unlisted is at least made legal: round to the nearest 3k+1 so
    # it names a set squarely instead of landing there by truncation.
    return min(GENESIS_SETS, key=lambda g: abs(g - deco)), False

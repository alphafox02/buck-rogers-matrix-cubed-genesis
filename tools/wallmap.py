# SPDX-License-Identifier: MIT
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


# Selecting the wall set is only half of it on the Genesis.
#
# LOADPIECES sets 0x9AFB, which drives the loader at 0x0976C -- the wall
# GRAPHICS. The wall PIECE TABLES at 0xB556/0xB55A come from a different
# loader at 0x08360, dispatched on 0xB52A, and 0xB52A comes from the region
# and from 0x97DC. Without those tables the engine returns from 0x0CCBA
# without ever computing 0x97AD, which is what a script reads to ask "what
# kind of place am I standing in" -- 80 sites across Matrix Cubed.
#
# The only thing that sets 0x97DC is `VIEW 4, 0x71` (-> 0xA8, set 2) or
# `VIEW 4, 0x72` (-> 0xA2, set 1). Matrix Cubed's areas say LOAD_AREA_DECO
# and never that, so they all fall to the default, set 3, which is one of
# the two cases in the table at 0x083D8 that fills no piece tables.
#
# So a deco that should behave like an interior gets a selector emitted
# after its LOADPIECES. Only decos listed here get one; an area left out
# keeps exactly the behaviour it had.
# EMPTY, and the reason is the point. Both selectors were tried on the
# opening dock, whose DOS deco is 5:
#
#   VIEW 4, 0x71  -> set 2, and 0x97AD reads 8 on every square of the dock
#   VIEW 4, 0x72  -> set 1, and 0x97AD reads 0 on every square
#
# A constant is the signature of a classification that means nothing. The
# piece table is Countdown's, the wall GRAPHICS are Matrix Cubed's (loaded
# separately by LOADPIECES through 0x0976C), and the sampler at 0x0CCF4
# classifies drawn tiles against the table -- so pairing one game's table
# with the other's graphics cannot produce a useful answer. Worse, the 0x71
# case reads 8 from the first step, which is the value the coronation
# summons waits for, so it fired before the player could move.
#
# Filling this in needs Matrix Cubed's OWN piece boundaries, out of
# WALLDEF1.DAX, injected as a table the engine can be pointed at. Until
# then an empty map leaves every area exactly as it was.
SELECTOR = {}


def selector(deco):
    """Genesis `VIEW 4` operand for a deco, or None to emit nothing."""
    return SELECTOR.get(deco)

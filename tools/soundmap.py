# SPDX-License-Identifier: MIT
"""
Translate DOS sound ids into ones the Genesis driver will act on.

The driver dispatches at 0x1B900 and rejects anything past the end of its
kind table:

    1B904: cmp.b #$4b, d0
    1B908: bhi.w $1b9ce        ; ignored, silently

Matrix Cubed's scripts call `SOUND_EVENT` with **0x81-0x86** for music --
ids above that ceiling -- so every music cue in the transplanted game was
being dropped and the only music that ever played was what Countdown's boot
code starts. That is why the areas are silent in play.

The Genesis music ids are the entries whose kind byte has bit 7 set:

    0x2C -> slot 0     0x2E -> slot 2     0x2F -> slot 3
    0x30 -> slot 9     0x31 -> slot 5     0x32 -> slot 6
    0x33 -> slot 7     0x34 -> slot 8     0x35 -> slot 4
    0x36 -> slot 10    0x25 -> slot 12

`0x2E` and `0x36` are left alone: the intro and the menu use them, and those
two slots already carry Matrix Cubed's music. The six DOS music cues take
the next six.

DOS effect ids (1-70) are passed through. They land in the driver's range
and produce *a* sound; whether it is the right one is a separate mapping
that has not been established, and a wrong effect is better than a hang.
"""

# There are exactly six music cues and seven songs in BUCKA.XMI, and the
# obvious reading holds: 0x8n plays song n, with song 0 the title theme the
# intro starts by itself. Nothing in the scripts names 0x80 or 0x87.
#
# Cue 0x86 goes to slot 10 rather than a slot of its own, because slot 10 is
# the menu and already carries song 6.
#
# DOS SOUND_EVENT id -> Genesis SOUND id
MUSIC = {
    0x81: 0x2F,     # song 1 -> music slot 3   (25 uses, 13 areas)
    0x82: 0x30,     # song 2 -> slot 9         (20 uses, 11 areas)
    0x83: 0x31,     # song 3 -> slot 5         (9 uses)
    0x84: 0x32,     # song 4 -> slot 6         (3 uses)
    0x85: 0x33,     # song 5 -> slot 7         (5 uses)
    0x86: 0x36,     # song 6 -> slot 10        (2 uses; shares the menu theme)
}

# The music slots those ids resolve to, and the BUCKA song each wants.
SLOTS = {0x2F: 3, 0x30: 9, 0x31: 5, 0x32: 6, 0x33: 7, 0x36: 10}
SONGS = {3: 1, 9: 2, 5: 3, 6: 4, 7: 5, 10: 6}

# Sound EFFECTS.
#
# These were passed through unchanged on the reasoning that a DOS id lands
# in the driver's range and makes *a* noise. One of them does worse than
# that: DOS effect 44 arrives as SOUND 0x2C, whose kind byte is 0x80 --
# music slot 0. A door or a gunshot restarts the soundtrack.
#
# There is no name table for either game's effects, so the mapping is made
# the way the monster one was: by what each sound plays over. Both engines'
# scripts were read for the line printed immediately after each call.
#
#   Countdown            Matrix Cubed
#   0x1B alarms blare    12 'ALARMS SOUND THROUGH THE PORT'
#   0x11 laser fire      17 'FIRING HIS LASER RIFLE MADLY'
#   0x06 engines roar     9 'A ROCKET BLASTS OFF'
#   0x04 apes shriek     14 'HUNTING VENUSIAN DINOSAURS CRASH TOWARDS YOU'
#   0x23 acid frogs       4 'BURNED BY THE ACID IN THE LAKE'
#   0x07 figure firing    6 'THE ASSASSIN', 8 'THE MARTIANS PULL THEIR W...'
#   0x1F weapons fire     3 'THE BARRICADE BEING BLOWN', 16 'RIPS APART'
#   0x1C sniper's beam   13 'A BARRAGE OF SONIC STUNNERS'
#   0x1E ECGs slam        1 'YOU HIT A SOLID FLOOR OF ARMOR PLATE'
#   0x1D generic, 29 uses 20 'THE COMPUTER COMES TO LIFE', and the rest
#
# Where a DOS sound has no clear counterpart it goes to 0x1D, the effect
# Countdown leans on most and the least likely to be jarring.
EFFECTS = {
     1: 0x1E,    # impact
     2: 0x1D,    # doors
     3: 0x1F,    # explosion            (40 uses, the most common)
     4: 0x23,    # acid
     5: 0x1D,    # general
     6: 0x07,    # gunfire              (29 uses)
     7: 0x1D,    # malfunction
     8: 0x07,    # gunfire
     9: 0x06,    # rocket engines
    10: 0x1F,    # blast
    11: 0x1F,    # thunder
    12: 0x1B,    # alarm                (17 uses)
    13: 0x1C,    # sonic stunner
    14: 0x04,    # big creature
    16: 0x1F,    # explosion
    17: 0x11,    # laser
    20: 0x1D,    # computer             (25 uses)
    44: 0x1D,    # would otherwise restart music slot 0
    63: 0x1D,    # computer
    70: 0x06,    # ship engines
}

CEILING = 0x4B      # the driver ignores anything above this


def translate(sid):
    """Return (genesis_id, kind) where kind is 'music', 'effect' or None."""
    if sid in MUSIC:
        return MUSIC[sid], "music"
    if sid in EFFECTS:
        return EFFECTS[sid], "effect"
    return sid, None

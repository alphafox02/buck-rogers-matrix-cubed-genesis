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

# DOS SOUND_EVENT id -> Genesis SOUND id
MUSIC = {
    0x81: 0x2F,     # -> music slot 3
    0x82: 0x30,     # -> slot 9
    0x83: 0x31,     # -> slot 5
    0x84: 0x32,     # -> slot 6
    0x85: 0x33,     # -> slot 7
    0x86: 0x34,     # -> slot 8
}

# The music slots those ids resolve to, for whoever fills them.
SLOTS = {0x2F: 3, 0x30: 9, 0x31: 5, 0x32: 6, 0x33: 7, 0x34: 8}

CEILING = 0x4B      # the driver ignores anything above this


def translate(sid):
    """Return (genesis_id, was_remapped)."""
    if sid in MUSIC:
        return MUSIC[sid], True
    return sid, False

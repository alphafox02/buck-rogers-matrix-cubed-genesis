"""
Guard Matrix Cubed's art references against the resources the ROM has.

The engine resolves art through two directories, both found by following
the `PICTURE` opcode rather than by guessing (see docs/re_notes.md):

    0x51326 / 0x51360   ECL pictures, 88x88 portraits, ids 0x20-0x6F
    0x51302 / 0x5130A   VIEW big pictures, 288x120, ids 0x70-0x78

An id neither directory holds sends the loader off the end of its id list,
which is not ignored -- it lands in the chunked decompressor and used to
stop the game. `tools/softfail.py` makes that non-fatal, but a blank is
still worse than a picture, so references that cannot resolve are rewritten
to 0xFF, which the loader tests for before doing any lookup:

    04DFA: move.b $b525.w, d0
    04DFE: bpl.b  $4e04         ; negative -> clear instead of load

An earlier version of this file guarded against the item icon table at
0xF14F2 and against which (mode, id) pairs stock Countdown happened to use.
Both were wrong: the icon table is a different resource entirely, and
VIEW's mode selects a drawing style, not a resource space. The mode is
irrelevant to whether an id resolves.

`tools/expand_pictures.py` adds ids to the picture directory, so the set
below is the stock one plus whatever build.py injects.
"""

NO_PICTURE = 0xFF

# Stock contents of the two directories.
PICTURES = (32, 35, 58, 59, 64, 65, 66, 67, 68, 70, 71, 75, 76, 77, 79, 80, 81, 82, 83, 84, 87, 88, 89, 92, 93, 60, 61, 69, 72, 73, 74, 62, 85, 86, 90, 91, 94, 95, 97, 105, 33, 34, 36, 37, 38, 39, 40, 41, 48, 49, 50, 111, 42, 43, 51, 52, 44)

BIGPICS = (112, 115, 116, 117, 118, 119, 120)

# Ids tools/expand_pictures.py adds; kept in step with build.PORTRAIT_IDS.
ADDED = (0x02, 0x04, 0x17, 0x1D, 0x1E, 0x1F, 0x37, 0x38, 0x39, 0x60, 0x62,
         0x63, 0x65, 0x66, 0x67, 0x68, 0x6A, 0x6B, 0x71, 0x72)

AVAILABLE = frozenset(PICTURES) | frozenset(BIGPICS) | frozenset(ADDED)


def picture(pid):
    """Return (id_to_emit, was_replaced) for a PICTURE operand."""
    if pid >= 0x80 or pid in AVAILABLE:
        return pid, False
    return NO_PICTURE, True


def view(mode, vid):
    """Return (id_to_emit, was_replaced) for VIEW's resource operand.

    `mode` is accepted and ignored: it selects how the picture is drawn, not
    where it comes from.
    """
    if vid >= 0x80 or vid in AVAILABLE:
        return vid, False
    return NO_PICTURE, True

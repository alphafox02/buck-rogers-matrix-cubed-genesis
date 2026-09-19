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

# Added to the VIEW directory by expand_pictures --bigpic, and injected
# in the same build, under the same rule as ADDED below.
BIG_ADDED = (113, 114, 0x79)

# Ids tools/expand_pictures.py adds, every one of which build.py also injects
# artwork for. The rule that matters is that the two lists stay equal: an
# added id with no art inherits the directory's first entry, which is the
# largest picture in the cartridge, and that is what crashed the first
# attempt at expanding this.
ADDED = (0x02, 0x04, 0x17, 0x1D, 0x1E, 0x1F, 0x37, 0x38, 0x39,
         0x60, 0x62, 0x63, 0x65, 0x66, 0x67, 0x68, 0x6A, 0x6B)

AVAILABLE = (frozenset(PICTURES) | frozenset(BIGPICS)
             | frozenset(ADDED) | frozenset(BIG_ADDED))


def picture(pid):
    """Return (id_to_emit, was_replaced) for a PICTURE operand."""
    if pid >= 0x80 or pid in AVAILABLE:
        return pid, False
    return NO_PICTURE, True


# In mode 4 the operand is not a picture at all -- it selects a wall set.
# The handler at 0x03DEA tests for exactly two values and writes neither to
# the picture register:
#
#     03DF0  cmp.b #$71, d0  ->  move.b #$A8, $97DC
#     03DFE  cmp.b #$72, d0  ->  move.b #$A2, $97DC
#     03E0C  move.b d0, $B525          anything else IS a picture
#
# and 0x97DC is what 0x082C6 reads to pick the wall set, which is what
# loads the piece tables at 0x0B556/0x0B55A, which is what the engine needs
# before it will compute 0x97AD at all.
#
# Matrix Cubed uses exactly two values in mode 4 -- 0x70 eleven times and
# 0x74 nine -- against Countdown's 0x71 and 0x72. Passed through, both fall
# out of the bottom of that handler and are drawn as pictures, so the wall
# set is never selected and every script gate on 0x97AD reads zero forever.
# Two selectors against two selectors, matched in order; that the counts
# pair up is a fact, that the order corresponds is the same kind of guess
# as tools/wallmap.py makes about the sets themselves, and it is one entry
# to repoint if an area's walls come out wrong.
WALL_SELECT = {0x70: 0x71, 0x74: 0x72}


def view(mode, vid):
    """Return (id_to_emit, was_replaced) for VIEW's resource operand.

    Apart from mode 4 above, `mode` is accepted and ignored: it picks a case
    in the jump table at 0x083D8, which decides how the picture is drawn,
    not where it comes from. Restricting it to modes stock Countdown uses
    was tried and was wrong -- Countdown exercises all five, and an earlier
    scan missed mode 3 only because it appears there with a variable
    operand.
    """
    if mode == 4 and vid in WALL_SELECT:
        return WALL_SELECT[vid], True
    if vid >= 0x80 or vid in AVAILABLE:
        return vid, False
    return NO_PICTURE, True

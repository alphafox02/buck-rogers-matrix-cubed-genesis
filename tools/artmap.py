"""
Guard Matrix Cubed's art references against Countdown's smaller resource set.

Matrix Cubed names pictures and views by id, and the Genesis cartridge does
not contain all of them. An id the ROM has no entry for makes the picture
loader read a bad offset, and the chunked decompressor at 0x09C10 then
overshoots its remaining-bytes counter:

    09C26: sub.w  d3, d6        ; remaining -= chunk
    09C28: bmi.w  $9cf6         ; negative -> "loadpieces error 1"

which is a hard stop. A play session hit it during the Sun King coronation.

Ids with the high bit set mean "no picture" rather than an index -- the
loader tests for it before doing any lookup:

    04DFA: move.b $b525.w, d0
    04DFE: bpl.b  $4e04         ; negative -> clear instead of load

so an unavailable id is rewritten to 0xFF. The scene then plays without its
artwork instead of killing the game. This is a stopgap: all 3430 Matrix
Cubed images are already converted (679 KB against 848 KB free), and once
they are injected this table should shrink to nothing.

Valid ids come from the directory itself, not from what Countdown's scripts
happen to use. `PICTURE` resolves through a 110-entry table of 4-byte
pointers at 0xF14F2 -- found by clustering every ROM location that points
at a decodable picture -- and all 110 entries decode, so ids 0..109 are
real. Only one Matrix Cubed id falls outside it.

An earlier version of this file allowed only the 33 ids Countdown's scripts
reference, which blanked 183 uses of perfectly valid art.
"""

NO_PICTURE = 0xFF

# The PICTURE directory: 110 pointers at 0xF14F2, so ids 0..109 resolve.
PICTURE_DIR = 0xF14F2
PICTURE_COUNT = 110

# Kept for reference: the ids Countdown's own scripts use.
PICTURES = (35, 37, 43, 50, 52, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 70, 71, 72, 73, 74, 75, 76, 79, 81, 85, 86, 91, 92, 93, 94, 95, 97, 255)

# VIEW's OPERAND PAIR, not just the id. The first operand is a mode, and the
# mode selects which resource space the id indexes: Countdown uses (4, 0x72)
# while Matrix Cubed uses (1, 0x72) -- the same id in a different archive.
# Checking the id alone let VIEW 1, 0x72 through, and that is the call that
# crashed a play session at the Sun King coronation. Countdown never uses
# mode 3 at all.
VIEW_PAIRS = ((0, 65), (0, 255), (1, 112), (1, 115), (1, 116), (1, 117), (1, 119), (1, 120), (2, 92), (2, 255), (4, 59), (4, 113), (4, 114))


# The figure directory at 0x09A14, {pointer, id, chunk, flags} records ended
# by a negative id. LOAD_MON and SPRITE_START name ids in this space, and a
# miss is not ignored: the search at 0x099CC runs off the end into 0x099F6
# and loads a garbage pointer, which lands in the chunked decompressor and
# stops the game with "loadpieces error 1". That is the crash a play session
# kept hitting when the Sun King coronation broke into combat.
MONSTERS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 58, 59, 60, 61, 62, 64)


def monster(mid):
    """Map a monster id onto one the figure directory actually holds.

    Substituting the nearest lower id keeps the encounter -- it fights with
    another creature's sprite -- where blanking it would drop the fight.
    """
    if mid in MONSTERS:
        return mid, False
    lower = [m for m in MONSTERS if m < mid]
    return (max(lower) if lower else min(MONSTERS)), True


def picture(pid):
    """Return (id_to_emit, was_replaced) for a PICTURE operand."""
    if pid >= 0x80 or pid < PICTURE_COUNT:
        return pid, False
    return NO_PICTURE, True


def view(mode, vid):
    """Return (id_to_emit, was_replaced) for VIEW's resource operand."""
    if vid >= 0x80 or (mode, vid) in VIEW_PAIRS:
        return vid, False
    return NO_PICTURE, True

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

Known-good ids are those stock Countdown's own scripts use, which are
demonstrably present. Regenerate with:

    python3 tools/artmap.py > tools/artmap.py.new
"""

NO_PICTURE = 0xFF

# Picture ids stock Countdown references, and therefore certainly has.
PICTURES = (35, 37, 43, 50, 52, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 70, 71, 72, 73, 74, 75, 76, 79, 81, 85, 86, 91, 92, 93, 94, 95, 97, 255)

# VIEW's second operand, same reasoning.
VIEWS = (59, 65, 92, 112, 113, 114, 115, 116, 117, 119, 120, 255)


def picture(pid):
    """Return (id_to_emit, was_replaced) for a PICTURE operand."""
    if pid >= 0x80 or pid in PICTURES:
        return pid, False
    return NO_PICTURE, True


def view(vid):
    """Return (id_to_emit, was_replaced) for VIEW's resource operand."""
    if vid >= 0x80 or vid in VIEWS:
        return vid, False
    return NO_PICTURE, True

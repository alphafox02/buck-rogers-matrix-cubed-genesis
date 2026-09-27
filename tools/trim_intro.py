# SPDX-License-Identifier: MIT
"""
End the intro after Matrix Cubed's title cards, and stop the attract demo.

Two four-byte patches, both inside the checksummed region, so the cartridge
sum is repaired afterwards.

**Trim the intro.** The sequence at 0x012FC shows two full-screen cards and
then stamps six overlays on top that tell Countdown's story -- the Doomsday
Laser, Earth, the RAM framing. Those are Countdown's, and replacing each with
something of our own would mean writing new art and new copy. Ending the
sequence instead is one instruction: the routine already has a skip path at
0x015F0 for a player pressing a button, and it unwinds cleanly.

    01400: moveq #$78, d0
    01402: jsr   $75fa.l      ; hold the MATRIX CUBED card
    01408: moveq #$6, d2      <- replaced with bra.w $15f0
    0140A: moveq #$11, d3

**Stop the attract demo.** Boot waits about 0x384 polls for input and, on a
timeout, sets 0xBA5A:

    00386: dbra  d2, $376
    0038A: st.b  $ba5a.w      <- replaced with clr.b $ba5a.w

The entry dispatch at 0x04146 reads that flag and sends the player into area
0x03, the ten-panel narration about NEO and RAM. Matrix Cubed has no attract
mode of its own -- nothing in its 33 ECL blocks or its executables matches
that narration -- so there is nothing to put in its place yet, and showing
the wrong game's story is worse than showing none. Clearing the flag instead
of setting it leaves the title up.

Both are single instructions of the same length, so nothing moves.

Usage:
    trim_intro.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integrity

# The title card waits for a button, and stock Countdown gives up after
# about fifteen seconds and plays the attract demo instead:
#
#     00366: jsr    $88c4        ; draw the card
#     00370: move.l #$384, d2    ; 900 frames
#     0037C: jsr    $f1b66       ; read the pad
#     00384: bne.b  $38e         ; pressed -> carry on
#     00386: dbra   d2, $376     ; else keep waiting
#     0038A: st.b   $ba5a.w      ; timed out -> demo
#     003A4: bne.b  $3b6         ; demo, or fall through to the menu
#
# Turning the demo off leaves that timeout falling straight through to the
# team menu, so the title screen appears to leave on its own after fifteen
# seconds. Making the wait unconditional restores what a player expects:
# the card stays up until a button is pressed.
WAIT = 0x00386
WAIT_ORIGINAL = bytes.fromhex("51caffee")     # dbra d2, $376
WAIT_FOREVER = bytes.fromhex("60ee4e71")      # bra.b $376 ; nop

OVERLAYS_AT = 0x01408        # first instruction of the overlay sequence
INTRO_EXIT = 0x015F0         # the routine's own skip path
ATTRACT_SET = 0x0038A        # st.b $ba5a.w on the input timeout

EXPECT_OVERLAY = bytes.fromhex("74067611")   # moveq #6,d2 / moveq #$11,d3
EXPECT_ATTRACT = bytes.fromhex("50f8ba5a")   # st.b $ba5a.w
CLR_ATTRACT = bytes.fromhex("4238ba5a")      # clr.b $ba5a.w


def wait_for_button(rom):
    if bytes(rom[WAIT:WAIT + 4]) != WAIT_ORIGINAL:
        raise SystemExit(f"0x{WAIT:05X} is not the title-card timeout")
    rom[WAIT:WAIT + 4] = WAIT_FOREVER
    print(f"  0x{WAIT:05X} dbra -> bra: the title card waits for a button "
          f"instead of timing out")


def apply(rom: bytes) -> bytes:
    rom = bytearray(rom)

    # NOT CUT. Branching out of the intro here was tried and freezes the
    # machine just as the second screen appears: the exit path at 0x015FC
    # frees the buffer at -4(a6), and the setup this skips is what leaves it
    # in a state that can be freed. The duplicate picture is dealt with by
    # giving the second screen different art instead.

    if bytes(rom[OVERLAYS_AT:OVERLAYS_AT + 4]) != EXPECT_OVERLAY:
        raise SystemExit(f"0x{OVERLAYS_AT:05X} is not the overlay sequence")
    disp = INTRO_EXIT - (OVERLAYS_AT + 2)
    rom[OVERLAYS_AT:OVERLAYS_AT + 2] = b"\x60\x00"
    struct.pack_into(">h", rom, OVERLAYS_AT + 2, disp)
    print(f"  0x{OVERLAYS_AT:05X}: overlays -> bra.w 0x{INTRO_EXIT:05X}")

    if bytes(rom[ATTRACT_SET:ATTRACT_SET + 4]) != EXPECT_ATTRACT:
        raise SystemExit(f"0x{ATTRACT_SET:05X} is not the attract trigger")
    rom[ATTRACT_SET:ATTRACT_SET + 4] = CLR_ATTRACT
    print(f"  0x{ATTRACT_SET:05X}: st.b $ba5a -> clr.b $ba5a (no attract demo)")

    # NOT APPLIED. wait_for_button turns the title card's fifteen-second
    # timeout into an unconditional wait, which is what the screen looks like
    # it should do. It was tried and made things worse: the boot reaches the
    # title TWICE -- there is a black teardown between them, so it is the
    # loop at 0x003D0 going back to 0x352 after the first entry into the game
    # returns instead of staying. With the stock timeout both passes expire
    # on their own and read as one slow sequence; with the wait they become
    # two button presses.
    #
    # The double entry is the real defect and it is not this patch's doing.
    # It could not be pinned down: BlastEm's -l logs each address once and
    # not in execution order, so it cannot count a redraw, and the pad cannot
    # be driven under logging to reproduce it. Left off until that can be
    # observed properly rather than guessed at.
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = apply(src.read_bytes())
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

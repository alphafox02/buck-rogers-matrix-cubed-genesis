# SPDX-License-Identifier: MIT
"""
Replace the intro screens.

The intro is a plain routine at `0x012FC`, not a directory: it plays a music
track, then loads screens by absolute address and draws them.

    01304: move.w #$2e, d0
    01308: jsr    $1b900.l      ; title music, track 0x2E
    01338: lea.l  $99b5f.l, a0  ; the SSI "presents" screen
    0133E: jsr    $9dd4.l
    0135A: moveq  #$28, d4      ; 40 tiles wide
    0135C: moveq  #$1c, d5      ; 28 tall -- 320x224, full screen
    013A8: lea.l  $96d4a.l, a0  ; the scene behind the titles, 320x200

Because each screen is named by a `lea` operand rather than looked up in a
table, replacing one is a matter of writing new artwork somewhere free and
pointing the operand at it. No directory grows, so none of the fallback
behaviour that made expanding the picture directory unsafe applies here.

The container is the one `docs/re_notes.md` describes, with the palette
flag the original used -- the intro screens set bit 2 where the ECL
pictures set bit 3; both mean a 16-word palette follows the nametable.

Size still matters: the stream carries no length and the engine expands it
into whatever is free, so a replacement stays within the original's
decompressed size. `inject_portrait.encode` does that by merging
near-identical tiles rather than dropping colours.

Usage:
    inject_title.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import genesis_ecl
import integrity
import inject_portrait as ip
import lzw_encode

from PIL import Image

# Above the portraits, which start at 0x1E0000 and now run to about
# 0x1F9600. This used to be 0x1F8000, chosen when there were fewer of them,
# and the title art silently overwrote pictures 0x6A and 0x6B -- the second
# of which is the shopkeeper, so walking into the shop showed the default
# space view instead of his face. Nothing errors: the portrait is written
# first and the title lands on top of it.
TITLE_BASE = 0x1FA000

# operand address, tiles wide, tiles tall, how to build the picture
SCREENS = (
    (0x0133A, 40, 28, "presents"),
    (0x013AA, 40, 25, "matrix"),
    (0x088FA, 36, 16, "menu"),
)

# What the menu card may spend, in unique tiles rather than bytes.
#
# The byte budget crushed this screen. Matrix Cubed's title art is a
# photograph of Jupiter -- 210 colours, no flat areas -- so 566 of its 576
# cells come out unique, and squeezing that into the 10086 bytes the
# Countdown card decompressed to took merge tolerance 32: half the tiles
# replaced by a neighbour differing in up to half its pixels. That is the
# smeared lettering and the checkerboarded moon.
#
# Nothing was ever measuring the right thing. The loader streams tiles to
# VRAM (see inject_portrait.encode), and this screen's tiles start at index
# 93 -- VDP register 2 puts plane A at 0xA000, so there is room to 1280.
# 1100 leaves margin for whatever the menu draws over the card.
#
# The card also gets all sixteen colours instead of the portraits' twelve:
# 0x088FE sets the [0xB4BD] one-shot immediately before the load, so this is
# one of the two screens whose whole palette reaches CRAM.
MENU_TILES = 1100


def compose_presents():
    """The Buck Rogers logo, centred and alone.

    Stacking the SSI banner, the logo and the copyright lines was tried, and
    they look bad together: three DOS images that each had their own palette
    have to share one line of sixteen colours here, and small text is what
    loses. Measured mean error 3.5 for the stack against 2.3 for the logo by
    itself, and the difference by eye is larger than that -- the logo stays
    crisp where the four-pixel-high copyright turns to mush.

    So the screen carries the thing that identifies the game and drops the
    fine print. The MATRIX CUBED card follows it.
    """
    out = Image.new("RGB", (320, 224), (0, 0, 0))
    logo = Image.open(REPO / "extracted" / "images" / "TITLE" / "002.png").convert("RGB")
    out.paste(logo, ((320 - logo.width) // 2, (224 - logo.height) // 2))
    return out


def compose_menu():
    """The card behind the main menu, drawn by 0x088C4 after the intro.

    This is the screen the stock game keeps on display with its copyright
    lines over it, and it was still Countdown's -- which is the "1991 Buck
    Rogers thing" that appeared after the new title cards.
    """
    out = Image.new("RGB", (288, 128), (0, 0, 0))
    src = Image.open(REPO / "extracted" / "images" / "TITLE" / "004.png").convert("RGB")
    src = src.resize((288, int(src.height * 288 / src.width)), Image.LANCZOS)
    out.paste(src, (0, (128 - src.height) // 2))
    return out


def compose_matrix():
    """The copyright card, centred.

    This slot used to carry MATRIX CUBED over Jupiter, which the menu card
    right after it also shows -- so the sequence ran the same picture twice,
    the large one first, and the large one is the worse of the two: a
    photographic gradient at 320x200 scores mean error 24 against sixteen
    colours where the smaller one has less to lose.

    Cutting the screen instead was tried and freezes the machine, because the
    intro's exit frees a buffer that the skipped setup is what prepares. So
    the screen stays and gets the one piece of Matrix Cubed's title art not
    used anywhere else: the copyright lines, which are a handful of colours
    on black and survive the palette intact.
    """
    out = Image.new("RGB", (320, 200), (0, 0, 0))
    src = Image.open(REPO / "extracted" / "images" / "TITLE" / "003.png").convert("RGB")
    out.paste(src, ((320 - src.width) // 2, (200 - src.height) // 2))
    return out


BUILD = {"presents": compose_presents, "matrix": compose_matrix,
         "menu": compose_menu}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    rom = bytearray(src.read_bytes())

    # One palette for the two intro screens. They are drawn by different
    # paths -- 0x08594 then 0x095BE for the first, 0x095BE alone for the
    # second -- and the second's own palette does not reliably reach CRAM,
    # so it was being drawn with the first screen's colours. Sharing a
    # palette makes that harmless instead of wrong.
    shared = ip.build_palette([BUILD["presents"](), BUILD["matrix"]()], 15)

    cursor = TITLE_BASE
    for operand, w, h, kind in SCREENS:
        old = struct.unpack_from(">I", rom, operand)[0]
        was = genesis_ecl.decompress(bytes(rom)[old:old + 0x40000], limit=0x40000)
        # The original of the second screen carries NO palette -- it inherits
        # whatever the screen before it set. Ours always brings one, so the
        # flag has to say so; keeping the original's 0x0000 made the length
        # disagree with the contents and the picture failed to decode.
        flags = struct.unpack_from(">HHH", was, 0)[2] or 0x0004
        if kind in ("presents", "matrix"):
            flags = 0x0004

        img = BUILD[kind]()
        if kind == "menu":
            pal, cap, budget = ip.build_palette([img], 15), MENU_TILES, None
        else:
            pal, cap, budget = shared, None, len(was)
        got = ip.encode([img], 1, w, h, budget=budget, flags=flags,
                        palette=pal, tiles=cap)
        if got is None:
            print(f"  {kind}: will not fit in {len(was)} bytes, left alone")
            continue
        blob, ntiles, colours = got
        packed = lzw_encode.compress(blob)
        if genesis_ecl.decompress(packed, limit=0x40000) != blob:
            sys.exit(f"{kind} does not round-trip")
        rom[cursor:cursor + len(packed)] = packed
        struct.pack_into(">I", rom, operand, cursor)
        print(f"  {kind}: {w}x{h} tiles, {ntiles} tiles, {colours} colours, "
              f"{len(blob)}/{len(was)} bytes -> {len(packed)} packed at 0x{cursor:06X} "
              f"(was 0x{old:06X})")
        cursor += len(packed) + 2

    out = integrity.repair(bytes(rom))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

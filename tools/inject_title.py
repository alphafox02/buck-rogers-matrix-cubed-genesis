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

TITLE_BASE = 0x1F8000        # clear of the portraits at 0x1E0000

# operand address, tiles wide, tiles tall, how to build the picture
SCREENS = (
    (0x0133A, 40, 28, "presents"),
    (0x013AA, 40, 25, "matrix"),
)


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


def compose_matrix():
    """MATRIX CUBED over Jupiter, letterboxed into the scene slot."""
    out = Image.new("RGB", (320, 200), (0, 0, 0))
    src = Image.open(REPO / "extracted" / "images" / "TITLE" / "004.png").convert("RGB")
    out.paste(src, (0, (200 - src.height) // 2))
    return out


BUILD = {"presents": compose_presents, "matrix": compose_matrix}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    rom = bytearray(src.read_bytes())

    cursor = TITLE_BASE
    for operand, w, h, kind in SCREENS:
        old = struct.unpack_from(">I", rom, operand)[0]
        was = genesis_ecl.decompress(bytes(rom)[old:old + 0x40000], limit=0x40000)
        # The original of the second screen carries NO palette -- it inherits
        # whatever the screen before it set. Ours always brings one, so the
        # flag has to say so; keeping the original's 0x0000 made the length
        # disagree with the contents and the picture failed to decode.
        flags = 0x0004

        img = BUILD[kind]()
        got = ip.encode([img], 1, w, h, budget=len(was), flags=flags)
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

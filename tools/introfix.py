"""
Put the port's intro in the order DOS uses.

DOS composites `TITLE.DAX` blocks 2 and 3 onto ONE screen -- the Buck Rogers
logo with the copyright lines beneath it -- then shows the credits, then the
title card. The port draws the logo and the copyright block as two separate
full screens, so the copyrights appear stranded on black, and it has no credits
screen at all. A play session described the middle screen as "only got the text
that should have been on the previous screen bottom", which is exactly right.

This does two things:

* **Merges the copyright lines into the logo screen.** Rows 23-27 of
  `0x1FA000` are a single uniform tile, so the text goes there, drawn in
  palette index 8 -- the blue the separate screen used.
* **Gives the freed second slot to the credits**, which is where DOS puts
  them. That slot is drawn 40x25, so the credits screen is built to 25 rows
  rather than the 28 a full screen gets.

Both screens are rebuilt and dropped in free space, and the two `lea` operands
in the intro at 0x012FC are repointed. `trim_intro.py`'s `bra.w $15f0` at
0x001408 is left in place: with the credits in the second slot there is nothing
to add after the title card.

The container layout, which `docs/re_notes.md` had recorded wrongly:

    u16 tile count, u16 nametable bytes, u16 palette mask
    nametable
    palettes -- 32 bytes per bit set in the mask, in CRAM line order
    tiles

and the loader at 0x09D66 uploads only entries **3 to 14** of each
(`subq.l #$3,d1 / addq.l #$6,a0`), so text drawn in index 1, 2 or 15 never
reaches CRAM and the screen comes up black.

Usage:
    introfix.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dosocr
import genesis_ecl
import integrity
import lzw_encode

REPO = Path(__file__).resolve().parent.parent

TITLE = 0x1FA000            # the Buck Rogers logo screen
TITLE_LEA = 0x00133A        # operand of `lea.l $1fa000.l, a0`
SECOND_LEA = 0x0013AA       # operand of `lea.l $1fb708.l, a0`
FREE, FREE_LIMIT = 0x1D3500, 0x1E0000
COLS = 40

COPYRIGHT = [
    "(C) 1992 TSR, INC.",
    "(C) 1992 THE DILLE FAMILY TRUST",
    "(C) 1992 STRATEGIC SIMULATIONS, INC.",
    "ALL RIGHTS RESERVED",
]
COPY_TOP = 23               # rows 23-26, all uniform on the shipped screen
COPY_INK = 8                # the blue the separate copyright screen used


def read(rom, addr):
    raw = genesis_ecl.decompress(rom[addr:], limit=0x20000)
    cnt, ntlen, mask = struct.unpack_from(">HHH", raw, 0)
    npal = bin(mask).count("1")
    nt = bytearray(raw[6:6 + ntlen])
    pal = raw[6 + ntlen:6 + ntlen + 32 * npal]
    tiles = [bytes(raw[6 + ntlen + 32 * npal + i * 32:][:32]) for i in range(cnt)]
    return nt, pal, tiles, mask


def build(nt, pal, tiles, mask):
    out = bytearray(struct.pack(">HHH", len(tiles), len(nt), mask))
    out += nt
    out += pal
    for t in tiles:
        out += t
    return bytes(out)


def glyph_tiles(lines, ink, bg, tiles):
    """Append tiles for `lines`, returning {(row, col): tile index}."""
    g = dosocr.glyphs()
    cache, placed = {}, {}
    for r, text in enumerate(lines):
        col0 = (COLS - len(text)) // 2
        for c, ch in enumerate(text.upper()):
            key = ch
            if key not in cache:
                bits = g.get(ch)
                t = bytearray([(bg << 4) | bg] * 32)
                if bits is not None:
                    for y in range(8):
                        for x in range(0, 8, 2):
                            hi = ink if bits[y][x] else bg
                            lo = ink if bits[y][x + 1] else bg
                            t[y * 4 + x // 2] = (hi << 4) | lo
                cache[key] = len(tiles)
                tiles.append(bytes(t))
            placed[(r, col0 + c)] = cache[key]
    return placed


def merge_title(rom):
    nt, pal, tiles, mask = read(rom, TITLE)
    first = struct.unpack_from(">H", nt, 0)[0]          # the uniform background
    bg_tile = first & 0x7FF
    bg = tiles[bg_tile][0] >> 4                         # its pixel index
    placed = glyph_tiles(COPYRIGHT, COPY_INK, bg, tiles)
    for (r, c), ti in placed.items():
        cell = (COPY_TOP + r) * COLS + c
        struct.pack_into(">H", nt, cell * 2, (first & 0xF800) | ti)
    print(f"  logo screen: {len(tiles)} tiles (was {len(tiles) - len(set(placed.values()))}),"
          f" copyright on rows {COPY_TOP}-{COPY_TOP + len(COPYRIGHT) - 1}")
    return build(nt, pal, tiles, mask)


def credits_screen(rows=25):
    import introcredits as ic
    ic.ROWS, ic.TOP = rows, 1
    tiles, nt = ic.tiles_and_map()
    return ic.container(tiles, nt)


def patch(rom: bytes, ssi=True):
    out = bytearray(rom)
    cursor = FREE

    def place(blob, label):
        nonlocal cursor
        packed = lzw_encode.compress(blob)
        if cursor + len(packed) > FREE_LIMIT:
            raise SystemExit("out of free space for the intro screens")
        out[cursor:cursor + len(packed)] = packed
        at = cursor
        print(f"  {label:16s} {len(blob):6d} -> {len(packed):5d} packed"
              f" at 0x{at:06X}")
        cursor += len(packed) + 16
        return at

    logo = place(merge_title(rom), "logo+copyright")
    struct.pack_into(">I", out, SECOND_LEA, place(credits_screen(), "credits"))

    if not ssi:
        struct.pack_into(">I", out, TITLE_LEA, logo)
        return bytes(out)

    struct.pack_into(">I", out, TITLE_LEA, place(ssi_screen(rom), "ssi presents"))
    struct.pack_into(">H", out, FIRST_WAIT, SSI_FRAMES)
    code = intro_block(NEW, logo, ROWS_FULL, 0xF0,
                       [("bsr", 0x085DA), ("bra", 0x0139E)])
    if NEW + len(code) > NEW_LIMIT:
        raise SystemExit(f"the logo block needs {len(code)} bytes,"
                         f" only {NEW_LIMIT - NEW} are dead")
    out[NEW:NEW + len(code)] = code
    out[HOOK:HOOK + 4] = _asm(HOOK, [("bra", NEW)])
    n = len(RESTART_WAS)
    if bytes(out[RESTART:RESTART + n]) == RESTART_WAS:
        out[RESTART:RESTART + n] = NOP * (n // 2)
        print(f"  music: restart at 0x{RESTART:05X} removed, one theme"
              f" carries the intro and the card")
    else:
        print(f"  music: 0x{RESTART:05X} is not the restart, left alone")
    print(f"  logo block: {len(code)} bytes at 0x{NEW:05X}"
          f" (room for {NEW_LIMIT - NEW}), entered from 0x{HOOK:05X}")
    return bytes(out)


# ---------------------------------------------------------------------------
# The SSI "presents" banner, which the port has never shown.
#
# DOS opens on it for about a second before the Buck Rogers logo. The port's
# intro has only two screen slots, so this adds a third out of the code
# `trim_intro.py` stranded: everything from 0x0140C to 0x015EF -- the two
# Countdown banner sequences -- is unreachable behind its `bra.w $15f0`, and
# 484 bytes is ample for one more load-and-draw. The flow becomes
#
#     block 1 (0x01338)  SSI banner, full screen, 72 frames
#     NEW     (0x0140C)  Buck Rogers logo + copyrights, full screen, 240
#     block 2 (0x0139E)  credits, 40x25, 120
#
# by pointing block 1's `lea` at the banner, shortening its wait, and
# replacing block 2's first instruction with a branch to NEW -- which ends by
# running that displaced instruction and dropping back in.
#
# NEW frees only -4(a6) (`bsr.w $1600`, the tail of 0x15fc): the allocator is a
# stack and that is the only handle it takes. Block 1 can afford `bsr.w $15fc`
# because the other two slots still hold the zeros 0x01324 wrote.
#
# The banner is quantised against the LOGO screen's palette rather than one of
# its own, so the two screens agree. That matters because the loader at 0x09D66
# uploads all sixteen entries only once -- see the note on [0xB4BD] -- and the
# second screen along gets entries 3 to 14.

SSI_ART = REPO / "extracted/images/TITLE/001.png"
ROWS_FULL = 28
SSI_FRAMES = 72             # DOS holds it about 1.2 seconds
FIRST_WAIT = 0x01384        # operand of block 1's `move.w #$f0, d0`
HOOK = 0x0139A              # `bsr.w $85da`, block 2's first instruction
NEW = 0x0140C               # first byte trim_intro.py made unreachable
NEW_LIMIT = 0x015F0

# DOS plays ONE theme across the whole intro and lets it run out shortly after
# the MATRIX CUBED card. The port restarted the music the moment the intro
# returned: 0x012FC plays event 0x2E (the title theme) and comes back after
# about seven seconds, and 0x0035C immediately starts event 0x36 (the menu
# theme) and holds the card under it for up to 900 frames.
#
# So the title theme was never heard past its first seven seconds, and giving
# it a stopping terminator changed nothing audible -- what plays over the card
# is the other track. Taking the restart out instead lets the one theme carry
# the intro, the card and the main menu, and stop on its own at 39.8 seconds,
# which is what a play session watching DOS described.
#
# The cost is that 0x00352 -- coming back to the card after a game ends --
# shares this code and is now silent. That is the same silence DOS has there.
RESTART = 0x0035C
RESTART_WAS = bytes.fromhex("303c00364eb90001b900")   # move.w #$36,d0; jsr
NOP = bytes.fromhex("4e71")

_REL = {"bsr": b"\x61\x00", "bra": b"\x60\x00", "bne": b"\x66\x00"}


def _asm(at, parts):
    """Lay bytes out at `at`, resolving ('bra', target) against the PC."""
    out = bytearray()
    for p in parts:
        if isinstance(p, bytes):
            out += p
            continue
        op, target = p
        out += _REL[op]
        out += struct.pack(">h", target - (at + len(out)))
    return bytes(out)


def intro_block(at, art, rows, frames, tail):
    """One load-and-draw, cut from the two the intro already has."""
    b = bytes.fromhex
    return _asm(at, [
        ("bsr", 0x085DA),
        b("11fc000e9bbc"),                       # move.b  #$e, $9bbc.w
        ("bsr", 0x08A76),
        b("41f9") + struct.pack(">I", art),      # lea.l   <art>.l, a0
        b("4eb900009dd4"),                       # jsr     $9dd4.l   decompress
        b("2d48fffc"),                           # move.l  a0, -$4(a6)
        b("7000720274007600") + bytes([0x78, COLS, 0x7A, rows]),
        b("31fcffffb510"),                       # move.w  #$ffff, $b510.w
        b("4278b512"), b("4278b50e"),
        b("206efffc"),                           # movea.l -$4(a6), a0
        b("4eb9000095be"),                       # jsr     $95be.l   draw
        b("4eb90000860e"),                       # jsr     $860e.l   show
        b("303c") + struct.pack(">H", frames),
        b("4eb9000075fa"),                       # jsr     $75fa.l   wait
        ("bsr", 0x01600),                        # free -$4(a6), and only that
        b("4a39ffffd8fc"),                       # tst.b   $ffffd8fc.l  skipped?
        ("bne", 0x015F0),
    ] + list(tail))


def cram_rgb(pal):
    """The sixteen colours of one CRAM line, as RGB."""
    out = []
    for i in range(16):
        w = struct.unpack_from(">H", pal, i * 2)[0]
        out.append((((w >> 1) & 7) * 255 // 7, ((w >> 5) & 7) * 255 // 7,
                    ((w >> 9) & 7) * 255 // 7))
    return out


def ssi_screen(rom):
    """The SSI banner on black, in the logo screen's own colours."""
    from PIL import Image
    nt0, pal, _tiles, mask = read(rom, TITLE)
    high = struct.unpack_from(">H", nt0, 0)[0] & 0xF800
    rgb = cram_rgb(pal[:32])

    img = Image.new("RGB", (COLS * 8, ROWS_FULL * 8), rgb[0])
    art = Image.open(SSI_ART).convert("RGB")
    img.paste(art, ((img.width - art.width) // 2, (img.height - art.height) // 2))
    px = img.load()

    def nearest(c):
        return min(range(16), key=lambda i: sum(
            (a - b) ** 2 for a, b in zip(rgb[i], c)))

    cache = {}
    tiles, index, nt, err = [], {}, bytearray(), 0
    for ty in range(ROWS_FULL):
        for tx in range(COLS):
            t = bytearray(32)
            for y in range(8):
                for x in range(0, 8, 2):
                    v = []
                    for dx in (x, x + 1):
                        c = px[tx * 8 + dx, ty * 8 + y]
                        if c not in cache:
                            cache[c] = nearest(c)
                        v.append(cache[c])
                        err += sum(abs(a - b) for a, b in zip(rgb[v[-1]], c))
                    t[y * 4 + x // 2] = (v[0] << 4) | v[1]
            t = bytes(t)
            if t not in index:
                index[t] = len(tiles)
                tiles.append(t)
            nt += struct.pack(">H", high | index[t])
    print(f"  ssi banner: {len(tiles)} unique tiles, mean error "
          f"{err / (COLS * ROWS_FULL * 64 * 3):.1f}")
    return build(nt, pal, tiles, mask)

if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = integrity.repair(patch(src.read_bytes()))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

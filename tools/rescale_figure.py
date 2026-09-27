# SPDX-License-Identifier: MIT
"""
Shrink a large-class figure so the combat board draws the whole creature.

Countdown's figure records carry a size class in the high nibble of byte 7:
class 0 is a 24x24 frame of nine cells, class 2 a 24x48 of eighteen, class 3
a 48x24. The ground-combat board, measured with `tools/bigprobe.py` and by
substituting a stock DESERT APE into the opening encounter, draws **nine
consecutive cells, three to a row** whatever the class says. A class 2 or 3
figure therefore appears on the board as a 24x24 crop -- the ape's head and
shoulders, the frog's back -- rather than the creature.

That matters to this port because three of the creatures it adds clone a
large donor and inherit its class:

    ASSAULT ROBOT  <- RAM ASSAULT BOT  class 3
    COMBAT ROBOT   <- RAM COMBAT BOT   class 3
    COYODORG       <- DESERT APE       class 2

The fix is not to give them a different donor -- that loses the creature --
but to redraw the donor at the size the board actually uses. Each frame is
decoded at its true shape, scaled to 24x24, and written back as a class 0
sheet: eighteen frames of nine cells, an atlas eighteen tiles wide.

Scaling is done on palette indices, not colours. The figure palette has no
ramps to interpolate along -- it is sixteen unrelated colours -- so an
averaged pixel would land on whatever index happened to be numerically
between two unrelated hues. Each output pixel takes the most common
non-transparent index in the box it covers, and stays transparent only if
every source pixel was.

Usage:
    rescale_figure.py <in.gen> <out.gen> 0x31 0x33 0x34
"""

import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import expand_figures
import genesis_ecl
import integrity
import lzw_encode

# Where rescaled sheets go. Clear of the monster stream at 0x1B1000, the
# figure directory at 0x1B4000 and the probe area at 0x1B7000.
SHEETS = 0x1B8000
SHEETS_LIMIT = 0x1C0000

SMALL_W, SMALL_H = 3, 3          # a class 0 frame, in tiles
ATLAS_W = 18                     # what every class 0 sheet uses
FRAMES = 18

# frame shape in tiles, by size class
SHAPE = {0: (3, 3), 2: (3, 6), 3: (6, 3)}


def read_sheet(rom, ptr):
    blob = genesis_ecl.decompress(rom[ptr:ptr + 0x30000], limit=0x30000)
    count = struct.unpack_from(">H", blob, 2)[0]
    cells = [struct.unpack_from(">H", blob, 6 + i * 2)[0]
             for i in range(count // 2)]
    return cells, blob[6 + count:]


def pixels(cells, tiles, fw, fh, frame):
    """One frame as a list of rows of palette indices."""
    out = [[0] * (fw * 8) for _ in range(fh * 8)]
    for c in range(fw * fh):
        n = frame * fw * fh + c
        if n >= len(cells):
            continue
        v = cells[n]
        t, hflip, vflip = v & 0x7FF, v & 0x800, v & 0x1000
        cx, cy, off = (c % fw) * 8, (c // fw) * 8, (v & 0x7FF) * 32
        for r in range(8):
            for col in range(4):
                if off + r * 4 + col >= len(tiles):
                    continue
                b = tiles[off + r * 4 + col]
                for k, idx in ((0, b >> 4), (1, b & 15)):
                    x, y = col * 2 + k, r
                    if hflip:
                        x = 7 - x
                    if vflip:
                        y = 7 - y
                    out[cy + y][cx + x] = idx
    return out


def shrink(frame, w, h, keep_aspect=False):
    """
    Box-filter on palette indices: the commonest opaque index wins.

    `keep_aspect` centres the creature horizontally and sits it on the
    bottom edge at its own proportions. It was tried and is worse: a 48x24
    robot becomes a half-height blob in the middle of an empty token, and
    the ape becomes a thin one. Stretching to fill matches what every stock
    24x24 creature does -- fill its frame -- so that is the default, and the
    option is left here because it is the right answer for anything that
    ever gets drawn next to a stock figure at the same scale.
    """
    sh, sw = len(frame), len(frame[0])
    if keep_aspect:
        scale = min(w / sw, h / sh)
        tw, th = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
        small = shrink(frame, tw, th, keep_aspect=False)
        out = [[0] * w for _ in range(h)]
        ox, oy = (w - tw) // 2, h - th
        for y in range(th):
            for x in range(tw):
                out[oy + y][ox + x] = small[y][x]
        return out
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            y0, y1 = y * sh // h, max(y * sh // h + 1, (y + 1) * sh // h)
            x0, x1 = x * sw // w, max(x * sw // w + 1, (x + 1) * sw // w)
            seen = collections.Counter(
                frame[sy][sx] for sy in range(y0, y1) for sx in range(x0, x1)
                if frame[sy][sx])
            out[y][x] = seen.most_common(1)[0][0] if seen else 0
    return out


def build(frames):
    """Pack 24x24 frames into a class 0 sheet."""
    tiles, order, cells = {}, [], []
    for f in frames:
        for cy in range(SMALL_H):
            for cx in range(SMALL_W):
                raw = bytearray()
                for r in range(8):
                    for col in range(4):
                        hi = f[cy * 8 + r][cx * 8 + col * 2]
                        lo = f[cy * 8 + r][cx * 8 + col * 2 + 1]
                        raw.append((hi << 4) | lo)
                key = bytes(raw)
                if key not in tiles:
                    tiles[key] = len(order)
                    order.append(key)
                cells.append(tiles[key])
    nt = b"".join(struct.pack(">H", t) for t in cells)
    return struct.pack(">HHH", len(order), len(nt), 0) + nt + b"".join(order)


def apply(rom: bytes, ids) -> bytes:
    rom = bytearray(rom)
    at = struct.unpack_from(">I", rom, expand_figures.OPERANDS[0])[0]
    recs, _ = expand_figures.read(bytes(rom), at)
    index = {r[4]: n for n, r in enumerate(recs)}

    cursor = SHEETS
    for fid in ids:
        if fid not in index:
            raise SystemExit(f"no figure 0x{fid:02X}")
        rec = bytearray(recs[index[fid]])
        klass = rec[7] >> 4
        if klass not in SHAPE:
            raise SystemExit(f"figure 0x{fid:02X} has class {klass}")
        if klass == 0:
            print(f"  figure 0x{fid:02X} is already class 0, left alone")
            continue
        fw, fh = SHAPE[klass]
        cells, tiles = read_sheet(bytes(rom), struct.unpack_from(">I", rec, 0)[0])
        have = len(cells) // (fw * fh)
        shrunk = [shrink(pixels(cells, tiles, fw, fh, f), 24, 24)
                  for f in range(min(FRAMES, have))]
        while len(shrunk) < FRAMES:
            shrunk.append(shrunk[-1])
        blob = build(shrunk)
        packed = lzw_encode.compress(blob)
        if cursor + len(packed) > SHEETS_LIMIT:
            raise SystemExit("rescaled sheets do not fit")
        rom[cursor:cursor + len(packed)] = packed
        struct.pack_into(">I", rec, 0, cursor)
        rec[5] = ATLAS_W
        rec[7] = rec[7] & 0x0F                       # class 0
        rom[at + index[fid] * 8:at + index[fid] * 8 + 8] = rec
        print(f"  figure 0x{fid:02X}: class {klass} {fw * 8}x{fh * 8} -> "
              f"class 0 24x24, {have} frames, {len(packed)} bytes at "
              f"0x{cursor:06X}")
        cursor += len(packed)

    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes(),
                [int(a, 0) for a in sys.argv[3:]])
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

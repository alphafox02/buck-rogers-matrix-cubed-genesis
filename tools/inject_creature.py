"""
Put a Matrix Cubed creature into the Genesis engine at its proper size.

`CPIC1.DAX` holds one pose per block at 24x24, 48x24 or 48x48, and the
Genesis engine draws a creature at 24x24, 24x48 or 48x24 depending on two
fields that must agree:

    figure record byte 7, high nibble   0 / 2 / 3
    monster record byte 0x23            1 / 2 / 3

Setting only the first draws a 24x24 crop of the artwork, which is what made
an earlier round of this look like the engine could not do large creatures
at all. Both are written here.

DOS colour is quantised to the sixteen the engine gives a combat figure
(`tools/figure_palette.json`, recovered by probing the hardware). The DOS
background colour -- whichever is commonest in the block -- becomes
transparent.

A DOS block is a single pose and the Genesis sheet wants eighteen frames, so
the poses given are cycled to fill it. That is enough to see a creature
standing and fighting; a real animation needs the frame grouping in
`docs/art_todo.md` finished first.

Usage:
    inject_creature.py <in.gen> <out.gen> <figure_id>:<class>:<block>[,<block>...]
"""

import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dax
import expand_figures
import gbimage
import genesis_ecl
import integrity
import lzw_encode

ART = 0x1BA000               # clear of the monster stream, directory and probes
ART_LIMIT = 0x1C8000
STREAM = 0x1B1000
FRAMES = 18

# frame shape in tiles, and the monster byte that must go with it
SHAPE = {0: (3, 3), 2: (3, 6), 3: (6, 3), 4: (6, 6)}
MONSTER_SIZE = {0: 1, 2: 2, 3: 3, 4: 4}


def palette():
    import json
    return [c and tuple(c) for c in
            json.load(open(Path(__file__).resolve().parent / "figure_palette.json"))]


def quantise(block, pal):
    """DOS block -> a grid of Genesis palette indices, 0 transparent."""
    from PIL import Image
    for _, w, h, pix in gbimage.frames(block):
        im = Image.frombytes("P", (w, h), bytes(pix))
        im.putpalette(gbimage.palette(block))
        im = im.convert("RGB")
        break
    else:
        raise SystemExit("block has no frames")
    counts = collections.Counter(im.getdata())
    bg = counts.most_common(1)[0][0]
    cache, out = {}, [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            c = im.getpixel((x, y))
            if c == bg:
                continue
            if c not in cache:
                best, bd = 0, 1 << 30
                for n, p in enumerate(pal):
                    if not p:
                        continue
                    d = sum((c[k] - p[k]) ** 2 for k in range(3))
                    if d < bd:
                        best, bd = n, d
                cache[c] = best
            out[y][x] = cache[c]
    return out


def fit(grid, w, h):
    """Box filter on palette indices -- the commonest opaque index wins."""
    sh, sw = len(grid), len(grid[0])
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            y0, y1 = y * sh // h, max(y * sh // h + 1, (y + 1) * sh // h)
            x0, x1 = x * sw // w, max(x * sw // w + 1, (x + 1) * sw // w)
            seen = collections.Counter(
                grid[sy][sx] for sy in range(y0, y1) for sx in range(x0, x1)
                if grid[sy][sx])
            out[y][x] = seen.most_common(1)[0][0] if seen else 0
    return out


def sheet(frames, fw, fh):
    """Frames of fw x fh tiles, cells row-major, into one sheet blob."""
    tiles, order, cells = {}, [], []
    for f in frames:
        for cy in range(fh):
            for cx in range(fw):
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


def apply(rom: bytes, specs) -> bytes:
    rom = bytearray(rom)
    pal = palette()
    cpic = dax.load(str(Path(__file__).resolve().parent.parent
                        / "dos_game" / "matrix" / "CPIC1.DAX"))

    at = struct.unpack_from(">I", rom, expand_figures.OPERANDS[0])[0]
    recs, _ = expand_figures.read(bytes(rom), at)
    index = {r[4]: n for n, r in enumerate(recs)}

    blob = bytearray(genesis_ecl.decompress(bytes(rom[STREAM:STREAM + 0x8000]),
                                            limit=0x8000))
    count = struct.unpack_from(">H", blob, 0)[0]
    ids = list(blob[2:2 + count])
    base = 2 + count
    REC = 214

    cursor = ART
    for spec in specs:
        fid, klass, blocks = spec.split(":")
        fid, klass = int(fid, 0), int(klass, 0)
        blocks = [int(b, 0) for b in blocks.split(",")]
        if fid not in index:
            raise SystemExit(f"no figure 0x{fid:02X}")
        fw, fh = SHAPE[klass]
        poses = [fit(quantise(cpic[b], pal), fw * 8, fh * 8) for b in blocks]
        frames = [poses[n % len(poses)] for n in range(FRAMES)]
        packed = lzw_encode.compress(sheet(frames, fw, fh))
        if cursor + len(packed) > ART_LIMIT:
            raise SystemExit("creature art does not fit")
        rom[cursor:cursor + len(packed)] = packed

        rec = bytearray(recs[index[fid]])
        struct.pack_into(">I", rec, 0, cursor)
        rec[5] = 36 if klass else 18
        rec[7] = (klass << 4) | (rec[7] & 0x0F)
        rom[at + index[fid] * 8:at + index[fid] * 8 + 8] = rec

        note = ""
        if fid in ids:
            off = base + ids.index(fid) * REC + 0x23
            was = blob[off]
            blob[off] = MONSTER_SIZE[klass]
            note = f", monster size {was} -> {blob[off]}"
        print(f"  figure 0x{fid:02X} <- CPIC1 {blocks}: class {klass} "
              f"{fw * 8}x{fh * 8}, {len(packed)} bytes at 0x{cursor:06X}{note}")
        cursor += len(packed)

    packed = lzw_encode.compress(bytes(blob))
    if STREAM + len(packed) > expand_figures.NEW_DIRECTORY:
        raise SystemExit("monster stream does not fit")
    rom[STREAM:STREAM + len(packed)] = packed
    return integrity.repair(bytes(rom))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    out = apply(Path(sys.argv[1]).read_bytes(), sys.argv[3:])
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

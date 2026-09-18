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

`--auto` works the mapping out instead of being told it. A DOS monster
record names its artwork at byte 185 -- `CARNIFERN` -> block 18, the plant
thing; `VENUS DINOSAUR` -> 22, the dinosaur; `AMALTH SEC BOT` -> 21, the
walker -- and a creature's two poses are blocks N and N+128, which holds for
every oversized block in the file. Matching each creature this port adds to
the DOS monster of the same name resolves 27 of 36.

Usage:
    inject_creature.py <in.gen> <out.gen> <figure_id>:<class>:<block>[,<block>...]
    inject_creature.py <in.gen> <out.gen> --auto
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

# Creature art sits between the figure directory and the relocated pictures.
#
# It used to start at 0x1BA000, which left 24 KB before inject_pic's own base
# at 0x1C0000, and adding a corpse frame to every creature pushed the last
# one 1,284 bytes past it -- straight over picture 0x70. tools/romlayout.py
# caught it and failed the build, which is what it is for. 0x1B5000 is clear
# of the 88-record figure directory at 0x1B4000 and gives 44 KB.
ART = 0x1B5000
ART_LIMIT = 0x1C0000         # inject_pic.ART_BASE

PICTURE = 185                # the DOS monster record's artwork byte
# `CPIC1` is the creature archive: 108 blocks, including every oversized
# creature, in N/N+128 pose pairs.
#
# It is the ONLY archive this reads, and that is a correction. Nine of the
# added creatures name a block CPIC1 does not have -- 0, 16, 20 and 28 --
# and the lookup used to fall back to `CHARS`, which does have all four.
# But CHARS is not a creature archive at all: its 36 blocks are the PLAYER
# character sprites, one per race/career/gender combination, which is why
# SECURITY ROBOT came out as a human with a sword. A monster picture id
# resolved there means nothing.
#
# A creature whose artwork does not resolve keeps the figure it cloned from
# Countdown instead, and those were picked by role, so the substitutes are
# close: SECURITY ROBOT clones RAM H.S. ROBOT, TECHNICIAN clones RAM
# TECHNICIAN, LOWLANDER clones LL. WARRIOR, DESERT RUNNER clones D.R.
# WARRIOR. Countdown's own art is simply better here than anything DOS
# offers, because the DOS art is not there.
#
# The five that name block 0 -- DESERT RUNNER, GANG RECRUIT, LOWLANDER,
# TECHNICIAN, WARRIOR -- are almost certainly "no picture of its own"
# rather than a missing file.
ARCHIVES = ("CPIC1.DAX",)
POSE = 128                   # a creature's second pose is block N + 128
SIZE_CLASS = {(24, 24): 0, (48, 24): 3, (48, 48): 4}
STREAM = 0x1B1000
FRAMES = 18

# frame shape in tiles, and the monster byte that must go with it
SHAPE = {0: (3, 3), 2: (3, 6), 3: (6, 3), 4: (6, 6)}
BIG = 4
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


# Where the engine keeps the death animation inside the 18-frame sheet.
#
# Rendering stock Countdown figures frame by frame -- 0x00 D.R. WARRIOR,
# 0x0C PIRATE WARRIOR, 0x1C RAM H.S. ROBOT -- gives the same shape every
# time: 0-8 stand and attack, 9-11 blank, 12-14 stand again, 15 is going
# down, 16 is flat on the floor, 17 stands. A creature killed in combat is
# drawn at 16 and stays there.
#
# A DOS block carries two poses and neither of them is a corpse, so filling
# all eighteen frames from those two left every dead creature standing up.
DYING, DEAD = 15, 16


def lie_down(grid, w, h):
    """A standing pose turned on its side, to stand in for a corpse.

    Rotated a quarter turn and refitted to the frame, which is exact for a
    24x24 creature and a squash for the oblong classes. Not the art SSI
    would have drawn, but it reads as a body on the floor rather than as a
    creature that shrugged off being killed.
    """
    sh, sw = len(grid), len(grid[0])
    turned = [[grid[sh - 1 - x][y] for x in range(sh)] for y in range(sw)]
    return fit(turned, w, h)


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


def sprite_blocks():
    """Every creature sprite block. See ARCHIVES for why that is CPIC1 only."""
    here = Path(__file__).resolve().parent.parent / "dos_game" / "matrix"
    out = {}
    for name in reversed(ARCHIVES):
        out.update(dax.load(str(here / name)))
    return out


def apply(rom: bytes, specs) -> bytes:
    rom = bytearray(rom)
    pal = palette()
    cpic = sprite_blocks()

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
        if klass == BIG:
            # A 2x2 creature is drawn as two three-row halves and the engine
            # puts the SECOND half on top: matching the halves against the
            # screen finds top-half art at y+24 and bottom-half art at y,
            # both pixel-exact, just swapped. Store them in the order it
            # reads them.
            poses = [p[fh * 4:] + p[:fh * 4] for p in poses]
        frames = [poses[n % len(poses)] for n in range(FRAMES)]
        corpse = lie_down(poses[0], fw * 8, fh * 8)
        frames[DYING] = frames[DEAD] = corpse
        packed = lzw_encode.compress(sheet(frames, fw, fh))
        if cursor + len(packed) > ART_LIMIT:
            raise SystemExit("creature art does not fit")
        rom[cursor:cursor + len(packed)] = packed

        rec = bytearray(recs[index[fid]])
        struct.pack_into(">I", rec, 0, cursor)
        # The sheet width matters for more than layout. The decoder remaps
        # the nametable from packed tile numbers to VRAM ids and computes
        # how many entries to rewrite as `d4 * width / 2` at 0x09C3E, with
        # d4 fixed at 18 by the caller's frame list. That equals the total
        # cell count only while the atlas is NINE rows deep, which every
        # stock sheet is: 18x9 and 36x9. A 648-cell sheet at 36 wide is
        # eighteen rows, so half of it keeps raw tile ids and draws whatever
        # those happen to hit -- which is why a 48x48 creature came out with
        # its head twice. Keep every atlas nine rows and the whole sheet is
        # remapped.
        rec[5] = (fw * fh * FRAMES) // 9
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


def auto():
    """Work out a spec for every added creature whose DOS artwork resolves."""
    import gbimage
    import monstermap
    here = Path(__file__).resolve().parent.parent / "dos_game" / "matrix"
    mon = dax.load(str(here / "MON0CHA.DAX"))
    cpic = sprite_blocks()
    size = {k: (gbimage.header(b)["width"], gbimage.header(b)["height"])
            for k, b in cpic.items() if len(b) >= 10}

    def name(b):
        return "".join(chr(c) for c in b[1:1 + b[0]] if 32 <= c < 127).strip()

    by_name = {}
    for k, b in mon.items():
        by_name.setdefault(name(b), k)

    specs = []
    for nid, (label, _src) in sorted(monstermap.NEW_CREATURES.items()):
        dos = by_name.get(label.strip())
        if dos is None:
            continue
        block = mon[dos][PICTURE]
        if block not in size or block + POSE not in size:
            continue
        klass = SIZE_CLASS.get(size[block])
        if klass is None:
            continue
        specs.append(f"0x{nid:02X}:{klass}:{block},{block + POSE}")
    return specs


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    args = auto() if sys.argv[3] == "--auto" else sys.argv[3:]
    out = apply(Path(sys.argv[1]).read_bytes(), args)
    Path(sys.argv[2]).write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; "
          f"wrote {sys.argv[2]}")

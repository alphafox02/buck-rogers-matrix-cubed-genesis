# SPDX-License-Identifier: MIT
"""
Convert Gold Box VGA artwork to Genesis format.

The gap between the two is the whole art problem:

    DOS      256 simultaneous colours from a 262,144-colour space (6 bits
             per channel), one byte per pixel
    Genesis  16 colours per palette, four palettes, from a 512-colour space
             (3 bits per channel), 4 bits per pixel in 8x8 planar tiles

So a conversion has to do three things, and the order matters:

 1. Reduce to 15 colours plus one reserved index. Done in a perceptual
    space, because RGB distance overweights green and produces muddy skies.
 2. Snap each palette entry to a colour the hardware can actually show.
    Snapping AFTER clustering rather than before keeps clusters honest --
    quantising first collapses distinct shades together and the clusterer
    then cannot tell them apart.
 3. Assign pixels to the final palette, optionally with error diffusion.

Dithering is off by default. It buys smoother gradients at the cost of a
speckle that reads as noise at Genesis resolution, and SSI's own Genesis art
does not use it.
"""

import struct
from collections import Counter

# Genesis CRAM is 3 bits per channel: eight levels, evenly spaced.
LEVELS = [0, 36, 73, 109, 146, 182, 219, 255]


def _snap_candidates():
    return [(r, g, b) for r in LEVELS for g in LEVELS for b in LEVELS]


_CANDIDATES = _snap_candidates()
_SNAP_CACHE = {}


def snap(rgb):
    """
    Nearest colour the VDP can display, preserving hue.

    Snapping each channel independently is the exact nearest neighbour under
    any per-channel metric -- the grid is a product space, so the distance
    decomposes. That is also its weakness: it can move two channels to the
    same level and destroy the relation between them.

        (80, 56, 48)  brown, R-G = 24
        -> (73, 73, 36)  olive, R-G = 0

    G=56 lies almost exactly between levels 36 and 73 (20 against 17). Taking
    73 is correct per-channel and wrong perceptually, because what made the
    colour brown was R being clearly above G. Choosing 36 costs three units
    of green and keeps the hue.

    So the search runs over all 512 displayable colours with a term for the
    differences between channels, which does not decompose and therefore
    cannot be done one channel at a time.
    """
    hit = _SNAP_CACHE.get(rgb)
    if hit is not None:
        return hit
    r, g, b = rgb
    dr, dg, db = r - g, g - b, r - b
    best, best_err = None, None
    for cand in _CANDIDATES:
        cr, cg, cb = cand
        flat = (0.30 * (cr - r) ** 2 + 0.59 * (cg - g) ** 2 + 0.11 * (cb - b) ** 2)
        hue = ((cr - cg) - dr) ** 2 + ((cg - cb) - dg) ** 2 + ((cr - cb) - db) ** 2
        err = flat + 0.5 * hue
        if best_err is None or err < best_err:
            best, best_err = cand, err
    _SNAP_CACHE[rgb] = best
    return best


def to_cram(rgb) -> int:
    """Pack to the VDP's 0000 BBB0 GGG0 RRR0 word."""
    r, g, b = (LEVELS.index(c) for c in snap(rgb))
    return (b << 9) | (g << 5) | (r << 1)


def _luma(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


# Perceptual channel weights. These belong on the SQUARED differences, not
# on the channel values before squaring -- scaling first squares the weights
# too, so blue would be penalised by 0.11^2 = 0.012 rather than 0.11, and a
# large blue error becomes almost free.
#
# That was a real defect, not a theoretical one: grey (56,56,56) was matching
# to (73,73,109) in preference to (36,36,36), because the 53-unit blue error
# cost less than the 20-unit error across all three channels. It drew a
# purple smear over dark backgrounds in every portrait.
_WEIGHTS = (0.30, 0.59, 0.11)


def _perceptual(c):
    """Channel values scaled for clustering, where relative spread is what matters."""
    return (c[0] * _WEIGHTS[0], c[1] * _WEIGHTS[1], c[2] * _WEIGHTS[2])


def _distance(a, b):
    return sum(w * (x - y) ** 2 for w, x, y in zip(_WEIGHTS, a, b))


def build_palette(pixels, size=15):
    """
    Median-cut in perceptual space, weighted by how often each colour occurs.

    Weighting matters: a portrait is mostly skin and background, and an
    unweighted cut spends entries on a few bright specular pixels.
    """
    counts = Counter(pixels)
    boxes = [list(counts.items())]
    while len(boxes) < size:
        # split the box with the widest perceptual spread
        target, axis, spread = None, 0, -1
        for box in boxes:
            if len(box) < 2:
                continue
            for ax in range(3):
                vals = [_perceptual(c)[ax] for c, _ in box]
                s = max(vals) - min(vals)
                if s > spread:
                    target, axis, spread = box, ax, s
        if target is None:
            break
        target.sort(key=lambda kv: _perceptual(kv[0])[axis])
        total = sum(n for _, n in target)
        acc, cut = 0, 1
        for i, (_, n) in enumerate(target):
            acc += n
            if acc >= total / 2:
                cut = max(1, min(i, len(target) - 1))
                break
        boxes.remove(target)
        boxes += [target[:cut], target[cut:]]

    palette = []
    for box in boxes:
        total = sum(n for _, n in box) or 1
        avg = tuple(sum(c[i] * n for c, n in box) / total for i in range(3))
        palette.append(snap(tuple(int(v) for v in avg)))
    # Deduplicate after snapping; two clusters can land on one hardware colour.
    seen, unique = set(), []
    for c in palette:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    while len(unique) < size:
        unique.append((0, 0, 0))
    return unique[:size]


def quantise(image, palette, dither=False):
    """Map an RGB image to palette indices. Index 0 is reserved."""
    w, h = image.size
    px = list(image.convert("RGB").getdata())
    out = bytearray(w * h)
    if not dither:
        cache = {}
        for i, c in enumerate(px):
            idx = cache.get(c)
            if idx is None:
                idx = 1 + min(range(len(palette)), key=lambda k: _distance(c, palette[k]))
                cache[c] = idx
            out[i] = idx
        return bytes(out)

    buf = [list(map(float, c)) for c in px]
    for y in range(h):
        for x in range(w):
            i = y * w + x
            cur = tuple(max(0, min(255, int(v))) for v in buf[i])
            k = min(range(len(palette)), key=lambda j: _distance(cur, palette[j]))
            out[i] = 1 + k
            err = [cur[c] - palette[k][c] for c in range(3)]
            for dx, dy, f in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    for c in range(3):
                        buf[ny * w + nx][c] += err[c] * f
    return bytes(out)


def to_tiles(indices, width, height):
    """Pack 8bpp indices into Genesis 4bpp 8x8 tiles, row-major."""
    tiles = []
    for ty in range(height // 8):
        for tx in range(width // 8):
            tile = bytearray()
            for y in range(8):
                row = ty * 8 + y
                for x in range(0, 8, 2):
                    col = tx * 8 + x
                    hi = indices[row * width + col] & 0xF
                    lo = indices[row * width + col + 1] & 0xF
                    tile.append((hi << 4) | lo)
            tiles.append(bytes(tile))
    return tiles


def dedupe(tiles):
    """Genesis art reuses tiles heavily; return (unique_tiles, tilemap)."""
    index, unique, tilemap = {}, [], []
    for t in tiles:
        if t not in index:
            index[t] = len(unique)
            unique.append(t)
        tilemap.append(index[t])
    return unique, tilemap


def convert(image, palette_index=0, dither=False):
    """Full conversion. Returns (palette, cram_words, tiles, tilemap, w, h)."""
    w, h = image.size
    w, h = w - w % 8, h - h % 8
    image = image.convert("RGB").crop((0, 0, w, h))
    palette = build_palette(list(image.getdata()))
    indices = quantise(image, palette, dither)
    tiles, tilemap = dedupe(to_tiles(indices, w, h))
    words = [(palette_index << 13) | t for t in tilemap]
    cram = [0] + [to_cram(c) for c in palette]
    return palette, cram, tiles, words, w, h


# --- multi-palette conversion -------------------------------------------
#
# A tilemap entry carries two bits of palette index, so a background can draw
# from four 15-colour palettes at once -- 60 colours, not 15. Using one
# palette for a whole image wastes three quarters of the hardware and loses
# any hue the picture does not spend most of its area on. In the Buck Rogers
# ship art that costs the blue eyes: every entry goes to orange hull.
#
# The approach is the standard one for this hardware: cluster tiles by the
# colours they contain, build a palette per cluster, then let each tile pick
# the palette that represents it best.

def _tile_colours(image, tx, ty):
    px = image.load()
    return [px[tx * 8 + x, ty * 8 + y] for y in range(8) for x in range(8)]


def _palette_error(colours, palette):
    return sum(min(_distance(c, p) for p in palette) for c in colours)


def convert_multi(image, palettes=4, dither=False, passes=3):
    """
    Convert using up to four hardware palettes.

    Returns (cram_sets, tiles, tilemap_words, width, height) where cram_sets
    is a list of CRAM word lists, one per palette.
    """
    w, h = image.size
    w, h = w - w % 8, h - h % 8
    image = image.convert("RGB").crop((0, 0, w, h))
    tw, th = w // 8, h // 8

    cells = [_tile_colours(image, tx, ty) for ty in range(th) for tx in range(tw)]

    # Seed by splitting tiles into bands of mean luma, which separates sky
    # from subject far better than an arbitrary initial assignment.
    order = sorted(range(len(cells)), key=lambda i: sum(_luma(c) for c in cells[i]))
    assign = [0] * len(cells)
    for rank, idx in enumerate(order):
        assign[idx] = min(palettes - 1, rank * palettes // max(1, len(cells)))

    pals = []
    for _ in range(passes):
        pals = []
        for p in range(palettes):
            pool = [c for i, cell in enumerate(cells) if assign[i] == p for c in cell]
            pals.append(build_palette(pool) if pool else [(0, 0, 0)] * 15)
        moved = 0
        for i, cell in enumerate(cells):
            sample = cell[::4]          # every fourth pixel is plenty to choose by
            best = min(range(palettes), key=lambda p: _palette_error(sample, pals[p]))
            if best != assign[i]:
                assign[i] = best
                moved += 1
        if not moved:
            break

    # Rebuild once more against the final assignment. Without this the last
    # iteration leaves palettes built for the PREVIOUS assignment while tiles
    # have already moved -- so a tile can be drawn with a palette chosen for
    # different tiles entirely. It showed up as a purple smear across dark
    # background tiles, which had been assigned a palette holding no dark
    # tone while a sibling palette held two.
    pals = []
    for p in range(palettes):
        pool = [c for i, cell in enumerate(cells) if assign[i] == p for c in cell]
        pals.append(build_palette(pool) if pool else [(0, 0, 0)] * 15)

    # Quantise each tile against its chosen palette.
    raw, words = [], []
    for ty in range(th):
        for tx in range(tw):
            i = ty * tw + tx
            p = assign[i]
            tile = bytearray()
            cell = _tile_colours(image, tx, ty)
            for y in range(8):
                for x in range(0, 8, 2):
                    a = 1 + min(range(len(pals[p])),
                                key=lambda k: _distance(cell[y * 8 + x], pals[p][k]))
                    b = 1 + min(range(len(pals[p])),
                                key=lambda k: _distance(cell[y * 8 + x + 1], pals[p][k]))
                    tile.append(((a & 0xF) << 4) | (b & 0xF))
            raw.append((bytes(tile), p))

    unique, index, words = [], {}, []
    for tile, p in raw:
        key = (tile, p)
        if key not in index:
            index[key] = len(unique)
            unique.append(tile)
        words.append((p << 13) | index[key])

    cram_sets = [[0] + [to_cram(c) for c in pal] for pal in pals]
    return cram_sets, unique, words, w, h

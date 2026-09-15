"""
Bulk-convert the extracted DOS artwork to Genesis tiles.

The conversion itself lives in `genesis_art.py`; this driver exists because
one conversion recipe does not fit all 3,430 images. The VDP draws art two
ways and they have different budgets:

  * Plane art (backgrounds). Each nametable entry carries two bits of
    palette index, so a full-screen picture may draw from up to four
    16-colour palettes at once. `convert_multi()` does that. How many it
    actually needs is measured per image rather than assumed -- see
    `convert_background()`.

  * Hardware sprites. A sprite's attribute word carries ONE palette index
    for the whole sprite, and colour 0 is transparent rather than a colour.
    Handing a sprite four palettes is meaningless -- it can only ever use
    one -- so sprites get a single palette built from their opaque pixels
    only.

Reserving index 0 is not a sprite-only concession. Index 0 is transparent
in *any* tile on *either* plane; what shows through is the backdrop colour
register. So every class here gets 15 usable colours per palette, and the
difference between a sprite and an opaque tile is only whether some source
colour is mapped onto that reserved index.

Classification rule (see docs/art_conversion.md for the evidence):

  background  BIGPIC1, TITLE, BACK1, and anything larger than 64x64.
              One to four palettes, whichever the picture earns. Nothing
              over 32x32 can be a single hardware sprite, so the big SHIPS
              pictures are plane art too.
  sprite      CPIC1, CHARS, COMSPR, 8X8D0, 8X8D1, CURSOR, and the SHIPS
              weapon/explosion frames. One palette, one keyed colour
              forced to index 0.
  tile        HITEK, LOTEK, MARSCOM, VENUSCOM, BORDERS and the SHIPS
              console panels. One palette, fully opaque. These are combat
              backdrop terrain and UI furniture: they tile edge to edge,
              so their dominant colour is real ground, not a key.

Usage:
    python3 convert_art.py                 # convert everything
    python3 convert_art.py --check         # also write side-by-side PNGs
    python3 convert_art.py --jobs 8
"""

import argparse
import json
import math
import struct
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import genesis_art as ga

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "extracted" / "images"
# VGADependentImages -- the portraits the picture window shows. They decode
# by a different path (tools/gbimage_vd.py) and land in their own tree, but
# they convert exactly like everything else. PIC1 is the archive the ECL
# PICTURE opcode indexes; its ids are the ones docs/art_todo.md is missing.
SRC_VD = ROOT / "extracted" / "images_vd"
DST = ROOT / "extracted" / "genesis_art"

MULTI_ARCHIVES = {"BIGPIC1", "TITLE", "BACK1"}

# The transparent colour each sprite set uses. These are engine conventions,
# not per-image guesses: the DOS art was authored against a fixed key and the
# whole archive shares it. Verified by eye on contact sheets of each set.
SPRITE_KEYS = {
    "CPIC1": (85, 85, 85),      # combat icons on VGA grey
    "CHARS": (85, 85, 85),
    "COMSPR": (85, 85, 85),
    "8X8D0": (0, 0, 0),         # overlay sparks / lights on black
    "8X8D1": (255, 85, 255),    # wall-detail overlays on VGA magenta
    "CURSOR": (255, 85, 255),
}

# SHIPS is the one mixed archive: weapon-effect frames keyed on black, and
# opaque console panels that merely happen to sit on a dark bezel. A border
# test separates them cleanly -- the effects score >= 0.87, the panels <= 0.25
# -- so it is a real gap, not a tuned threshold.
SHIPS_KEY = (0, 0, 0)
SHIPS_BORDER_MIN = 0.85


def border_fraction(image, colour):
    w, h = image.size
    px = image.load()
    edge = ([px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)]
            + [px[0, y] for y in range(1, h - 1)]
            + [px[w - 1, y] for y in range(1, h - 1)])
    return sum(1 for c in edge if c == colour) / max(1, len(edge))


def classify(archive, image):
    """Return (kind, key_rgb_or_None)."""
    w, h = image.size
    if archive in MULTI_ARCHIVES or max(w, h) > 64:
        return "background", None
    if archive in SPRITE_KEYS:
        return "sprite", SPRITE_KEYS[archive]
    if archive == "SHIPS":
        if border_fraction(image, SHIPS_KEY) >= SHIPS_BORDER_MIN:
            return "sprite", SHIPS_KEY
        return "tile", None
    return "tile", None


# --- single-palette conversion with a reserved key ------------------------
#
# genesis_art.convert() builds its palette from every pixel, which is wrong
# for a keyed sprite: the key covers 70% of a typical CPIC1 icon, and a
# frequency-weighted median cut happily spends several of the fifteen entries
# on shades of it. Excluding keyed pixels first is what makes a 24x24 sprite
# keep its face.

def convert_keyed(image, key):
    w, h = image.size
    w, h = w - w % 8, h - h % 8
    image = image.convert("RGB").crop((0, 0, w, h))
    pixels = list(image.get_flattened_data())
    opaque = [c for c in pixels if c != key] if key else pixels
    palette = ga.build_palette(opaque)

    cache = {}
    indices = bytearray(w * h)
    for i, c in enumerate(pixels):
        idx = cache.get(c)
        if idx is None:
            if key is not None and c == key:
                idx = 0
            else:
                idx = 1 + min(range(len(palette)),
                              key=lambda k: ga._distance(c, palette[k]))
            cache[c] = idx
        indices[i] = idx

    tiles, tilemap = ga.dedupe(ga.to_tiles(bytes(indices), w, h))
    cram = [[0] + [ga.to_cram(c) for c in palette]]
    return cram, tiles, list(tilemap), w, h, [palette], indices


def compact(cram_sets, words):
    """Drop palettes no tile references, and renumber the tilemap."""
    live = sorted({(w >> 13) & 3 for w in words})
    if len(live) == len(cram_sets):
        return cram_sets, words
    remap = {old: new for new, old in enumerate(live)}
    words = [(remap[(w >> 13) & 3] << 13) | (w & 0x7FF) for w in words]
    return [cram_sets[i] for i in live], words


def convert_background(image):
    """
    Pick the smallest palette count that is not visibly worse.

    Four palettes is the ceiling, not the answer. Half of this game's
    backgrounds contain fewer than fifteen distinct hardware colours once
    snapped, so splitting them four ways buys nothing -- and every palette a
    background does not claim is one the sprites drawn over it can have.
    So: convert at 1, 2, 3 and 4 palettes and take the fewest whose error is
    within 2% of the best. 2% is deliberately tight -- the story art in
    BIGPIC1 has nothing drawn over it and should keep every colour it can.
    """
    tried = []
    for n in (1, 2, 3, 4):
        if n == 1:
            _pal, cram, tiles, words, w, h = ga.convert(image)
            crams = [cram]
        else:
            crams, tiles, words, w, h = ga.convert_multi(image, palettes=n)
            crams, words = compact(crams, words)
        blob = pack_gart("background", crams, tiles, words, w, h, None)
        err = mean_error(image.convert("RGB").crop((0, 0, w, h)),
                         render(unpack_gart(blob)), None)
        tried.append((err, crams, tiles, words, w, h))
        if err == 0.0:
            break
    floor = min(t[0] for t in tried)
    trial = [round(t[0], 3) for t in tried]
    for t in tried:
        if t[0] <= floor * 1.02 or t[0] == floor:
            return t[1:] + (trial,)
    return tried[-1][1:] + (trial,)


# --- container ------------------------------------------------------------
#
# .gart: everything needed to hand one picture to the VDP, big-endian
# because the consumer is a 68000.
#
#   0  4  magic 'GART'
#   4  1  version (1)
#   5  1  kind  0 background / 1 sprite / 2 tile
#   6  1  palette_count (1 or 4)
#   7  1  flags  bit0 = index 0 is a keyed transparent colour
#   8  2  width in pixels
#  10  2  height in pixels
#  12  2  tile columns (width / 8)
#  14  2  tile rows (height / 8)
#  16  2  unique tile count
#  18  3  the source key colour, r,g,b (zero when flags bit0 clear)
#  21  3  padding
#  24  .. palette_count * 16 CRAM words
#  ..  .. unique_tiles * 32 bytes, VDP 4bpp order (high nibble = left pixel)
#  ..  .. columns*rows nametable words: 000 PP 00 <11-bit tile index>
#
# The tile index in the nametable is relative to the start of this image's
# tile data; whoever uploads it adds the VRAM base.

MAGIC = b"GART"
KINDS = {"background": 0, "sprite": 1, "tile": 2}


def pack_gart(kind, cram_sets, tiles, words, w, h, key):
    cols, rows = w // 8, h // 8
    flags = 1 if key is not None else 0
    kr, kg, kb = key if key is not None else (0, 0, 0)
    out = bytearray()
    out += MAGIC
    out += struct.pack(">BBBB", 1, KINDS[kind], len(cram_sets), flags)
    out += struct.pack(">HHHHH", w, h, cols, rows, len(tiles))
    out += struct.pack(">BBB", kr, kg, kb) + b"\0\0\0"
    for cram in cram_sets:
        entries = list(cram) + [0] * (16 - len(cram))
        out += struct.pack(">16H", *entries[:16])
    for t in tiles:
        out += t
    out += struct.pack(f">{len(words)}H", *words)
    return bytes(out)


def unpack_gart(blob):
    assert blob[:4] == MAGIC, "not a .gart"
    ver, kind, npal, flags = struct.unpack_from(">BBBB", blob, 4)
    w, h, cols, rows, ntiles = struct.unpack_from(">HHHHH", blob, 8)
    key = struct.unpack_from(">BBB", blob, 18) if flags & 1 else None
    off = 24
    crams = []
    for _ in range(npal):
        crams.append(list(struct.unpack_from(">16H", blob, off)))
        off += 32
    tiles = [blob[off + i * 32: off + i * 32 + 32] for i in range(ntiles)]
    off += ntiles * 32
    words = list(struct.unpack_from(f">{cols * rows}H", blob, off))
    return dict(kind=kind, npal=npal, key=key, w=w, h=h, cols=cols, rows=rows,
                crams=crams, tiles=tiles, words=words)


def from_cram(word):
    b = (word >> 9) & 7
    g = (word >> 5) & 7
    r = (word >> 1) & 7
    return (ga.LEVELS[r], ga.LEVELS[g], ga.LEVELS[b])


def render(info):
    """Rebuild an RGB image from a decoded .gart, exactly as the VDP would."""
    w, h = info["w"], info["h"]
    img = Image.new("RGB", (w, h))
    px = img.load()
    pals = [[from_cram(c) for c in cram] for cram in info["crams"]]
    for ty in range(info["rows"]):
        for tx in range(info["cols"]):
            word = info["words"][ty * info["cols"] + tx]
            pal = pals[(word >> 13) & 3] if info["npal"] > 1 else pals[0]
            tile = info["tiles"][word & 0x7FF]
            for y in range(8):
                for x in range(0, 8, 2):
                    byte = tile[y * 4 + x // 2]
                    px[tx * 8 + x, ty * 8 + y] = pal[byte >> 4]
                    px[tx * 8 + x + 1, ty * 8 + y] = pal[byte & 0xF]
    return img


# --- error metric ---------------------------------------------------------

def mean_error(original, rebuilt, key):
    """
    RMS distance in the same perceptual space the quantiser optimises.

    Keyed pixels are excluded: a sprite's transparent area is not drawn, so
    counting it would flatter every sprite with a big background.
    """
    a = list(original.convert("RGB").get_flattened_data())
    b = list(rebuilt.get_flattened_data())
    total, n = 0.0, 0
    for oc, rc in zip(a, b):
        if key is not None and oc == key:
            continue
        total += ga._distance(oc, rc)
        n += 1
    if not n:
        return 0.0
    return math.sqrt(total / n)


# --- worker ---------------------------------------------------------------

def convert_one(args):
    archive, path = args
    rel = Path(path)
    try:
        image = Image.open(rel).convert("RGB")
        w0, h0 = image.size
        kind, key = classify(archive, image)

        trial = None
        if kind == "background":
            crams, tiles, words, w, h, trial = convert_background(image)
        else:
            crams, tiles, words, w, h, _pals, _idx = convert_keyed(image, key)

        blob = pack_gart(kind, crams, tiles, words, w, h, key)
        dest = DST / archive / (rel.stem + ".gart")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)

        rebuilt = render(unpack_gart(blob))
        cropped = image.crop((0, 0, w, h))
        err = mean_error(cropped, rebuilt, key)

        total_tiles = (w // 8) * (h // 8)
        return dict(
            archive=archive, name=rel.stem, kind=kind,
            src_w=w0, src_h=h0, w=w, h=h,
            cropped_x=w0 - w, cropped_y=h0 - h,
            palettes=len(crams), key=list(key) if key else None,
            tiles_total=total_tiles, tiles_unique=len(tiles),
            src_colours=len(Counter(image.get_flattened_data())),
            dos_bytes=w0 * h0,
            gart_bytes=len(blob),
            tile_bytes=len(tiles) * 32,
            map_bytes=total_tiles * 2,
            pal_bytes=len(crams) * 32,
            mean_err=round(err, 3),
            palette_trial_err=trial,
            error=None,
        )
    except Exception as exc:  # a failed image must not stop the run
        return dict(archive=archive, name=rel.stem, kind=None, error=f"{type(exc).__name__}: {exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=0, help="worker processes (0 = cpu count)")
    ap.add_argument("--check", action="store_true", help="write side-by-side comparison PNGs")
    ap.add_argument("--only", help="convert one archive only")
    args = ap.parse_args()

    jobs = []
    for root in (SRC, SRC_VD):
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or (args.only and d.name != args.only):
                continue
            for f in sorted(d.glob("*.png")):
                jobs.append((d.name, str(f)))
    print(f"{len(jobs)} images")

    import time
    t0 = time.time()
    with Pool(args.jobs or None) as pool:
        results = []
        for i, r in enumerate(pool.imap_unordered(convert_one, jobs, chunksize=8), 1):
            results.append(r)
            if i % 250 == 0:
                print(f"  {i}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)
    elapsed = time.time() - t0

    results.sort(key=lambda r: (r["archive"], r["name"]))
    DST.mkdir(parents=True, exist_ok=True)
    (DST / "manifest.json").write_text(json.dumps(
        dict(elapsed_seconds=round(elapsed, 1), images=results), indent=1))
    ok = [r for r in results if not r["error"]]
    bad = [r for r in results if r["error"]]
    print(f"converted {len(ok)}, failed {len(bad)}, {elapsed:.0f}s")
    for r in bad:
        print("  FAIL", r["archive"], r["name"], r["error"])

    if args.check:
        write_checks(ok)


CHECK_PICKS = [
    # backgrounds, easy and hard
    ("BIGPIC1", "113"), ("BIGPIC1", "112"), ("BIGPIC1", "114"),
    ("TITLE", "004"), ("TITLE", "001"), ("BACK1", "001"),
    ("SHIPS", "000"), ("SHIPS", "004"), ("SHIPS", "128"),
    # sprites
    ("CPIC1", "001"), ("CPIC1", "017"), ("CHARS", "000"), ("COMSPR", "001"),
    ("SHIPS", "014"), ("8X8D1", "001_04"), ("8X8D0", "001_00"),
    # opaque tile sets
    ("MARSCOM", "001_00"), ("HITEK", "001_00"), ("LOTEK", "001_04"),
    ("VENUSCOM", "001_00"), ("BORDERS", "000_00"),
]


def write_checks(results, extra=8):
    out = DST / "_check"
    out.mkdir(parents=True, exist_ok=True)
    picks = list(CHECK_PICKS)
    worst = sorted((r for r in results if r["tiles_total"] > 4),
                   key=lambda r: -r["mean_err"])[:extra]
    picks += [(r["archive"], r["name"]) for r in worst]
    seen = set()
    for archive, name in picks:
        if (archive, name) in seen:
            continue
        seen.add((archive, name))
        gart = DST / archive / f"{name}.gart"
        src = SRC / archive / f"{name}.png"
        if not src.exists():
            src = SRC_VD / archive / f"{name}.png"
        if not gart.exists():
            print("  missing", gart)
            continue
        info = unpack_gart(gart.read_bytes())
        rebuilt = render(info)
        original = Image.open(src).convert("RGB").crop((0, 0, info["w"], info["h"]))
        scale = max(2, min(8, 400 // max(1, info["w"])))
        gap = 8
        w, h = info["w"] * scale, info["h"] * scale
        sheet = Image.new("RGB", (w * 2 + gap, h), (255, 0, 255))
        sheet.paste(original.resize((w, h), Image.NEAREST), (0, 0))
        sheet.paste(rebuilt.resize((w, h), Image.NEAREST), (w + gap, 0))
        sheet.save(out / f"{archive}_{name}.png")
    print(f"wrote {len(seen)} comparisons to {out}")


if __name__ == "__main__":
    main()

"""
Put Matrix Cubed's portraits into the Genesis ECL picture directory.

This is the directory the `PICTURE` opcode actually uses -- `0x51326` for
the ids, `0x51360` for the pointers -- found by following the opcode through
`0x03662` -> `0x04DFA` -> `0x08516` -> `0x0B7B4`. The item icon table at
`0xF14F2` is a different thing entirely; writing art there replaces the
inventory icons.

Container:

     0  2  unique tile count
     2  2  nametable size in bytes
     4  2  flags -- bit 3 means a palette follows the nametable
     6  .. nametable, tile index in bits 0-10, palette line in bits 13-14
    ..  32 sixteen CRAM words, when flags bit 3 is set
    ..  .. tile data, 32 bytes each

**The palette travels with the image.** That is what makes this worth doing:
the earlier attempt had to borrow whatever palette an area had loaded, and
measured 63 mean error against 21 for an image's own sixteen colours. Here
each portrait brings its own.

Portraits are 11x11 tiles -- 88x88 pixels, exactly the size of the DOS
originals -- repeated for each animation frame. The frame count of the
picture being replaced is preserved, since the animation metadata at
`0x51444` is left alone and describes how many frames to expect.

Usage:
    inject_portrait.py <in.gen> <out.gen> <id>:<archive>/<name> ...
"""

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import genesis_ecl
import integrity
import lzw_encode

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")

# The directory address is read from the loader's own operands, so this
# works both before and after tools/expand_pictures.py relocates the tables.
IDS_OPERAND, PTRS_OPERAND, META_OPERAND = 0x0B7C2, 0x0B7C8, 0x0B7CE
BIG_IDS_OPERAND, BIG_PTRS_OPERAND = 0x0B768, 0x0B76E

# Big pictures are a single 36x15-tile frame, 288x120. The DOS originals are
# 304x120, so eight pixels come off each side rather than scaling -- the
# heights already match and a resize would soften every edge.
BIG_W, BIG_H = 36, 15
CELLS = 121              # 11x11 tiles
SIDE = 11
# Above the relocated directory tables at 0x1B0000. Twenty-eight
# portraits run to roughly 90 KB, so starting at 0x1A0000 overran them.
# Where injected artwork goes. The relocated directory tables sit at
# 0x1B0000; big pictures and portraits each get their own region so one
# cannot overrun the other, which happened once and left the pointers
# reading nonsense.
ART_BASE = 0x1C0000        # big pictures
PORTRAIT_BASE = 0x1E0000   # portraits
# The flag bit does not merely say "a palette follows" -- it says WHICH CRAM
# line that palette is loaded into. Bit 2 means line 2, bit 3 means line 3.
# The nametable has to reference the same line in bits 13-14 or the picture
# is drawn with somebody else's colours: the injected title came out in
# blues and pinks because its palette went to line 2 while its cells asked
# for line 0.
FLAG_PALETTE = 0x0008
PALETTE_LINE = {0x0004: 2, 0x0008: 3}


def directory(rom, big=False):
    ids_at = struct.unpack_from(">I", rom, BIG_IDS_OPERAND if big else IDS_OPERAND)[0]
    ptrs_at = struct.unpack_from(">I", rom, BIG_PTRS_OPERAND if big else PTRS_OPERAND)[0]
    meta_at = None if big else struct.unpack_from(">I", rom, META_OPERAND)[0]
    ids, a = [], ids_at
    while rom[a] < 0x80:
        ids.append(rom[a])
        a += 1
    return ids, ptrs_at, meta_at


def shape_of(rom, ptrs_at, slot):
    """(frame count, decompressed size) of the picture currently in this slot."""
    ptr = struct.unpack_from(">I", rom, ptrs_at + slot * 4)[0]
    blob = genesis_ecl.decompress(rom[ptr:ptr + 0x20000], limit=0x20000)
    _, map_bytes, _ = struct.unpack_from(">HHH", blob, 0)
    return (map_bytes // 2) // CELLS, len(blob)


def cram(rgb):
    """Nearest Genesis colour: three bits per channel, stored as even nibbles."""
    r, g, b = (min(7, max(0, round(v / 36))) for v in rgb)
    return (b << 9) | (g << 5) | (r << 1), (r * 36, g * 36, b * 36)


def build_palette(images, colours=15):
    """One palette for every frame of a picture, at most `colours` used."""
    merged = Image.new("RGB", (images[0].width * len(images), images[0].height))
    for i, im in enumerate(images):
        merged.paste(im, (i * im.width, 0))
    quant = merged.quantize(colors=colours, method=Image.MEDIANCUT)
    # An image with fewer distinct colours than asked for returns a shorter
    # palette, so it is padded rather than indexed off the end.
    raw = quant.getpalette() or []
    raw = (raw + [0] * 45)[:45]
    words, rgb = [0x0000], [(0, 0, 0)]      # index 0 is the backdrop
    for i in range(15):
        w, c = cram(tuple(raw[i * 3:i * 3 + 3]))
        words.append(w)
        rgb.append(c)
    return words, rgb


def _similar(key, order, tolerance):
    """Index of an existing tile differing in at most `tolerance` pixels."""
    best, bd = None, tolerance + 1
    for i, other in enumerate(order):
        d = 0
        for a, b in zip(key, other):
            if a != b:
                d += (1 if (a >> 4) != (b >> 4) else 0) + (1 if (a & 15) != (b & 15) else 0)
                if d >= bd:
                    break
        if d < bd:
            best, bd = i, d
            if d == 0:
                break
    return best


def nearest(px, rgb):
    best, bd = 0, None
    for i, (pr, pg, pb) in enumerate(rgb):
        d = (0.30 * (px[0] - pr)) ** 2 + (0.59 * (px[1] - pg)) ** 2 + (0.11 * (px[2] - pb)) ** 2
        if bd is None or d < bd:
            best, bd = i, d
    return best


def encode(images, frames, w=SIDE, h=SIDE, budget=None, flags=FLAG_PALETTE,
           palette=None):
    """Build (blob, tile count, colours) for one picture, or None if it cannot fit.

    `budget` is the DECOMPRESSED size of the picture being replaced. The
    compressed stream carries no length of its own, so the engine expands it
    into whatever memory happens to be free; a blob bigger than the original
    overruns that, and BlastEm halts with a write above 0xDFFFFE.

    Fewer colours make more tiles come out identical and share, which shrinks
    the blob without cropping or scaling the picture. If even three colours
    will not fit, nothing is injected and the original stays -- a picture
    that is merely Countdown's beats one that crashes the game.
    """
    while len(images) < frames:
        images.append(images[len(images) % len(images)] if images else images[0])
    images = images[:frames]
    blob, ntiles = _encode_at(images, w, h, 15, 0, flags, palette)
    if budget is None or len(blob) <= budget:
        return blob, ntiles, 15

    # Over budget. Merging near-identical tiles costs far less than dropping
    # colours: a picture reduced to three colours is unrecognisable, where
    # sharing a tile whose neighbour differs in two pixels is invisible at
    # this size. Tolerance rises until it fits.
    for tol in range(1, 33):
        blob, ntiles = _encode_at(images, w, h, 15, tol, flags, palette)
        if len(blob) <= budget:
            return blob, ntiles, 15
    # Only if merging cannot do it does the palette narrow.
    for colours in (13, 11, 9, 7):
        blob, ntiles = _encode_at(images, w, h, colours, 16, flags, palette)
        if len(blob) <= budget:
            return blob, ntiles, colours
    return None


def _encode_at(images, w, h, colours, tolerance=0, flags=FLAG_PALETTE, palette=None):
    words, rgb = palette if palette else build_palette(images, colours)

    tiles, order, nm = {}, [], []
    for im in images:
        px = im.convert("RGB").load()
        idx = [[nearest(px[x, y], rgb) for x in range(w * 8)] for y in range(h * 8)]
        for ty in range(h):
            for tx in range(w):
                raw = bytearray()
                for y in range(8):
                    for x in range(0, 8, 2):
                        hi = idx[ty * 8 + y][tx * 8 + x]
                        lo = idx[ty * 8 + y][tx * 8 + x + 1]
                        raw.append((hi << 4) | lo)
                key = bytes(raw)
                if key not in tiles:
                    hit = _similar(key, order, tolerance) if tolerance else None
                    if hit is None:
                        tiles[key] = len(order)
                        order.append(key)
                    else:
                        tiles[key] = hit
                nm.append(tiles[key] | (PALETTE_LINE.get(flags, 3) << 13))

    blob = struct.pack(">HHH", len(order), len(nm) * 2, flags)
    blob += b"".join(struct.pack(">H", e) for e in nm)
    blob += b"".join(struct.pack(">H", x) for x in words)
    blob += b"".join(order)
    return blob, len(order)


def sources(path):
    """Every frame of a picture, in order."""
    d, name = path.split("/")
    base = REPO / "extracted" / ("images" if d == "BIGPIC1" else "images_vd")
    if not (base / d).exists():
        base = REPO / "extracted" / "images"
    exact = base / d / f"{name}.png"
    if exact.exists():
        return [Image.open(exact).convert("RGB")]
    got = sorted((base / d).glob(f"{name}_*.png"), key=lambda p: p.stem)
    return [Image.open(p).convert("RGB") for p in got]


def main():
    big = "--bigpic" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--bigpic"]
    if len(argv) < 3:
        sys.exit(__doc__)
    src, dst, specs = Path(argv[0]), Path(argv[1]), argv[2:]
    rom = bytearray(src.read_bytes())
    ids, ptrs_at, meta_at = directory(bytes(rom), big)
    # Each picture has an animation script alongside it, and it is written
    # against the picture that was there: a count byte, then entries the
    # loader indexes with at 0x0B800. A replacement with a different tile
    # layout makes those entries address frames that no longer exist, which
    # is what froze the team screen. Replaced pictures are pointed at a
    # zero-count script -- the portrait still shows, it simply does not
    # animate -- rather than inventing a format that has not been reversed.
    still = None
    if meta_at is not None:
        for k in range(len(ids)):
            m = struct.unpack_from(">I", rom, meta_at + k * 4)[0]
            if rom[m] == 0:
                still = m
                break
    # Slots expand_pictures.py added all share one placeholder pointer; those
    # take their frame count from the artwork instead of from what was there.
    seen = {}
    for k in range(len(ids)):
        p = struct.unpack_from(">I", rom, ptrs_at + k * 4)[0]
        seen.setdefault(p, []).append(k)
    placeholder = {k for p, ks in seen.items() if len(ks) > 1 for k in ks[1:]}

    cursor = ART_BASE if big else PORTRAIT_BASE
    for spec in specs:
        pid, path = spec.split(":", 1)
        pid = int(pid, 0)
        if pid not in ids:
            print(f"  picture 0x{pid:02X}: not in the directory, skipped")
            continue
        imgs = sources(path)
        if not imgs:
            print(f"  picture 0x{pid:02X}: no image for {path}, skipped")
            continue
        slot = ids.index(pid)
        was_frames, budget = shape_of(bytes(rom), ptrs_at, slot)
        if slot in placeholder:
            # A slot expand_pictures.py added: the placeholder it points at
            # is a real picture, and its size is the budget to stay under.
            was_frames = 1 if big else len(imgs)
        if big:
            crop = []
            for im in imgs[:1]:
                x0 = max(0, (im.width - BIG_W * 8) // 2)
                crop.append(im.crop((x0, 0, x0 + BIG_W * 8, BIG_H * 8)))
            frames = 1
            got = encode(crop, 1, BIG_W, BIG_H, budget)
        else:
            frames = was_frames
            got = encode(imgs, frames, budget=budget)
        if got is None:
            print(f"  picture 0x{pid:02X}: {path} will not fit in {budget} bytes, left alone")
            continue
        blob, ntiles, colours = got
        packed = lzw_encode.compress(blob)
        if genesis_ecl.decompress(packed, limit=0x40000) != blob:
            sys.exit(f"compressed {path} does not round-trip")
        rom[cursor:cursor + len(packed)] = packed
        struct.pack_into(">I", rom, ptrs_at + slot * 4, cursor)
        if still is not None:
            struct.pack_into(">I", rom, meta_at + slot * 4, still)
        print(f"  picture 0x{pid:02X}: {path} x{frames}, {ntiles} tiles, {colours} colours, "
              f"{len(blob)}/{budget} bytes -> {len(packed)} packed at 0x{cursor:06X}"
              + ("" if still is None else ", animation cleared"))
        cursor += len(packed) + 2

    out = integrity.repair(bytes(rom))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

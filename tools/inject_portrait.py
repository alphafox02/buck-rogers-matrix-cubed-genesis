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
IDS_OPERAND, PTRS_OPERAND = 0x0B7C2, 0x0B7C8
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
FLAG_PALETTE = 0x0008


def directory(rom, big=False):
    ids_at = struct.unpack_from(">I", rom, BIG_IDS_OPERAND if big else IDS_OPERAND)[0]
    ptrs_at = struct.unpack_from(">I", rom, BIG_PTRS_OPERAND if big else PTRS_OPERAND)[0]
    ids, a = [], ids_at
    while rom[a] < 0x80:
        ids.append(rom[a])
        a += 1
    return ids, ptrs_at


def frames_of(rom, ptrs_at, slot):
    """How many 88x88 frames the picture in this slot has."""
    ptr = struct.unpack_from(">I", rom, ptrs_at + slot * 4)[0]
    blob = genesis_ecl.decompress(rom[ptr:ptr + 0x20000], limit=0x20000)
    _, map_bytes, _ = struct.unpack_from(">HHH", blob, 0)
    return (map_bytes // 2) // CELLS


def cram(rgb):
    """Nearest Genesis colour: three bits per channel, stored as even nibbles."""
    r, g, b = (min(7, max(0, round(v / 36))) for v in rgb)
    return (b << 9) | (g << 5) | (r << 1), (r * 36, g * 36, b * 36)


def build_palette(images):
    """One sixteen-colour palette for every frame of a picture."""
    merged = Image.new("RGB", (images[0].width * len(images), images[0].height))
    for i, im in enumerate(images):
        merged.paste(im, (i * im.width, 0))
    quant = merged.quantize(colors=15, method=Image.MEDIANCUT)
    raw = quant.getpalette()[:45]
    words, rgb = [0x0000], [(0, 0, 0)]      # index 0 is the backdrop
    for i in range(15):
        w, c = cram(tuple(raw[i * 3:i * 3 + 3]))
        words.append(w)
        rgb.append(c)
    return words, rgb


def nearest(px, rgb):
    best, bd = 0, None
    for i, (pr, pg, pb) in enumerate(rgb):
        d = (0.30 * (px[0] - pr)) ** 2 + (0.59 * (px[1] - pg)) ** 2 + (0.11 * (px[2] - pb)) ** 2
        if bd is None or d < bd:
            best, bd = i, d
    return best


def encode(images, frames, w=SIDE, h=SIDE):
    """Build (blob, tile count) for one picture."""
    while len(images) < frames:
        images.append(images[len(images) % len(images)] if images else images[0])
    images = images[:frames]
    words, rgb = build_palette(images)

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
                    tiles[key] = len(order)
                    order.append(key)
                nm.append(tiles[key])

    blob = struct.pack(">HHH", len(order), len(nm) * 2, FLAG_PALETTE)
    blob += b"".join(struct.pack(">H", e) for e in nm)
    blob += b"".join(struct.pack(">H", w) for w in words)
    blob += b"".join(order)
    return blob, len(order)


def sources(path):
    """Every frame of a picture, in order."""
    d, name = path.split("/")
    base = REPO / "extracted" / ("images" if d == "BIGPIC1" else "images_vd")
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
    ids, ptrs_at = directory(bytes(rom), big)
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
        if big:
            crop = []
            for im in imgs[:1]:
                x0 = max(0, (im.width - BIG_W * 8) // 2)
                crop.append(im.crop((x0, 0, x0 + BIG_W * 8, BIG_H * 8)))
            blob, ntiles = encode(crop, 1, BIG_W, BIG_H)
            frames = 1
        else:
            frames = len(imgs) if slot in placeholder else frames_of(bytes(rom), ptrs_at, slot)
            blob, ntiles = encode(imgs, frames)
        packed = lzw_encode.compress(blob)
        if genesis_ecl.decompress(packed, limit=0x40000) != blob:
            sys.exit(f"compressed {path} does not round-trip")
        old = struct.unpack_from(">I", rom, ptrs_at + slot * 4)[0]
        rom[cursor:cursor + len(packed)] = packed
        struct.pack_into(">I", rom, ptrs_at + slot * 4, cursor)
        print(f"  picture 0x{pid:02X}: {path} x{frames} frames, {ntiles} tiles, "
              f"{len(packed)} packed at 0x{cursor:06X} (was 0x{old:06X})")
        cursor += len(packed) + 2

    out = integrity.repair(bytes(rom))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")


if __name__ == "__main__":
    main()

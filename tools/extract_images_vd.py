# SPDX-License-Identifier: MIT
"""
Render "VGA dependent" DAX image blocks to PNG.

The companion to `extract_images.py`, which handles only the plain VGA
format. `PIC1`, `SPRIT1`, `PIC7` and `PIC8` are stored differently -- the
game configuration calls the format `VD` -- and `gbimage.py` rejects them at
the header check. Between them the two extractors cover the whole archive.

This matters more than the file count suggests. `PIC1` is the archive the
ECL `PICTURE` opcode indexes, so it holds every character portrait in the
game: Buck Rogers, Chancellor de Sade, the Terran leader with the PURGE ring.
`tools/inject_portrait.py` reads its output, which means without this the
build cannot put a face in the picture window.

The decoding lives in `gbimage_vd.py`; this is only the driver that walks the
archives and writes the frames out, and it mirrors `extract_images.py` so the
two trees are laid out the same way:

    extracted/images_vd/PIC1/032.png        a single-frame picture
    extracted/images_vd/PIC1/039_00.png     one frame of an animated one

Usage:
    python3 extract_images_vd.py <out_dir> <file.DAX> [...]

    python3 tools/extract_images_vd.py extracted/images_vd \\
        dos_game/matrix/PIC1.DAX dos_game/matrix/SPRIT1.DAX \\
        dos_game/matrix/PIC7.DAX dos_game/matrix/PIC8.DAX
"""

import sys
from pathlib import Path

import dax
import gbimage_vd

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")


def looks_like_image(block: bytes) -> bool:
    """Reject blocks whose header cannot describe a sane image.

    Same purpose as the check in extract_images.py and the same reasoning: a
    DAX archive holds whatever the game put in it, and a block that is not a
    picture will still decode into something. Bounding the dimensions and the
    frame count is what stops a table of numbers being written out as art.
    """
    if len(block) < 12:
        return False
    try:
        h = gbimage_vd.header(block)
    except Exception:
        return False
    if not (1 <= h["height"] <= 256 and 8 <= h["width"] <= 640):
        return False
    if not 1 <= h["image_count"] <= 256:
        return False
    return h["base_image"] < h["image_count"]


def main(sources, out_dir):
    out = Path(out_dir)
    written = skipped = 0
    for src in sources:
        name = Path(src).stem
        for block_id, block in sorted(dax.load(src).items()):
            if not looks_like_image(block):
                skipped += 1
                continue
            try:
                pal = gbimage_vd.palette(block)
                got = list(gbimage_vd.frames(block))
            except Exception:
                skipped += 1
                continue
            if not got:
                skipped += 1
                continue
            dest = out / name
            dest.mkdir(parents=True, exist_ok=True)
            multi = gbimage_vd.header(block)["image_count"] > 1
            for i, w, h, px in got:
                img = Image.new("P", (w, h))
                img.frombytes(px)
                img.putpalette(pal)
                # Single digit, not zero padded. This matches the tree the
                # format was first decoded into, and matching matters: a
                # rebuild that wrote 039_00.png beside an existing 039_0.png
                # would leave both, and inject_portrait.py globs "<id>_*.png",
                # so every animated picture would come out with its frames
                # doubled.
                suffix = f"_{i}" if multi else ""
                img.convert("RGB").save(dest / f"{block_id:03d}{suffix}.png")
                written += 1
    print(f"wrote {written} images to {out}/  "
          f"(skipped {skipped} non-image blocks)")
    return written


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: extract_images_vd.py <out_dir> <file.DAX> [...]")
    main(sys.argv[2:], sys.argv[1])

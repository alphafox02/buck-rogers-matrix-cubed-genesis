# SPDX-License-Identifier: MIT
"""
Render Gold Box DAX image blocks to PNG.

Usage:
    python3 extract_images.py <out_dir> <file.DAX> [...]

Format details and evidence: docs/formats.md
"""

import sys
from pathlib import Path

import dax
import gbimage

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")


def looks_like_image(block: bytes) -> bool:
    """Reject blocks whose header cannot describe a sane image."""
    if len(block) < 10:
        return False
    h = gbimage.header(block)
    if not (1 <= h["height"] <= 256 and 8 <= h["width"] <= 640):
        return False
    if not 1 <= h["image_count"] <= 256:
        return False
    if h["color_base"] + h["color_count"] > 256:
        return False
    size = h["width"] * h["height"] * h["image_count"]
    # Pixel data must fit, and must leave room for header + palette.
    return 10 + h["color_count"] * 3 <= len(block) - size


def main(sources, out_dir):
    out = Path(out_dir)
    written = skipped = 0
    for src in sources:
        name = Path(src).stem
        for block_id, block in sorted(dax.load(src).items()):
            if not looks_like_image(block):
                skipped += 1
                continue
            pal = gbimage.palette(block)
            dest = out / name
            dest.mkdir(parents=True, exist_ok=True)
            count = 0
            for i, w, h, px in gbimage.frames(block):
                img = Image.new("P", (w, h))
                img.frombytes(px)
                img.putpalette(pal)
                suffix = f"_{i:02d}" if gbimage.header(block)["image_count"] > 1 else ""
                img.convert("RGB").save(dest / f"{block_id:03d}{suffix}.png")
                count += 1
            written += count
    print(f"wrote {written} images to {out}/  (skipped {skipped} non-image blocks)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: extract_images.py <out_dir> <file.DAX> [...]")
    main(sys.argv[2:], sys.argv[1])

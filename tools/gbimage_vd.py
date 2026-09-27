# SPDX-License-Identifier: MIT
"""
Gold Box "VGA dependent" image decoder — the format Matrix Cubed uses for
its portraits and sprites.

`PIC1.DAX`, `SPRIT1.DAX`, `PIC7` and `PIC8` are not the plain VGA images that
`gbimage.py` handles. The game configuration calls them `VD`, and they carry
a different header, a second palette-mapping table, and a further layer of
compression inside the DAX block.

Layout:

    u16  height
    u16  width / 8
    u16  x placement
    u16  y placement
    u8   image_count - 1
    u8   colour_base
    u8   colour_count
    ...  colour_count * 3 bytes of 6-bit VGA palette
    ...  colour_count / 2 bytes mapping VGA indices to EGA ones
    4    unrecognised
    u8   index of the base image
    1    unrecognised
    ...  3 bytes per image, packed sizes
    ...  RLE data for every frame, concatenated

The RLE is a near-relative of the DAX container's, differing in one detail
that matters: the repeat branch also stores count-1, so a run is `count + 1`
long in BOTH branches. Decoding it with the container's rule desynchronises
after the first run.

Frames after the first are stored as XOR deltas against the base frame,
which is why block sizes vary so widely for what are nominally fixed-size
portraits.

Structure cross-checked against farmboy0/ssi-engine
(`data/image/VGADependentImages.java`), read as documentation.
"""

import struct


def header(block: bytes) -> dict:
    h = {
        "height":      struct.unpack_from("<H", block, 0)[0],
        "width":       struct.unpack_from("<H", block, 2)[0] * 8,
        "x":           struct.unpack_from("<H", block, 4)[0] * 8,
        "y":           struct.unpack_from("<H", block, 6)[0] * 8,
        "image_count": 1 + block[8],
        "color_base":  block[9],
        "color_count": block[10],
    }
    n = h["color_count"]
    # palette, then the EGA mapping table, then two unrecognised runs with
    # the base-image index between them, then one packed size per frame.
    pos = 11 + 3 * n + (n >> 1) + 4
    h["base_image"] = block[pos]
    h["data"] = pos + 2 + 3 * h["image_count"]
    return h


def decompress(data: bytes, want: int) -> bytes:
    """RLE where both branches store count-1."""
    out = bytearray()
    i = 0
    while i < len(data) and len(out) < want:
        c = data[i]
        i += 1
        if c < 0x80:                       # literal run of c+1
            out += data[i:i + c + 1]
            i += c + 1
        else:                              # repeat, also count+1
            n = 0x100 - c
            if i >= len(data):
                break
            out += bytes([data[i]]) * (n + 1)
            i += 1
    return bytes(out)


def palette(block: bytes) -> list:
    """Flat 768-entry RGB list for PIL, honouring colour_base."""
    h = header(block)
    pal = [0] * 768
    for i in range(h["color_count"]):
        idx = h["color_base"] + i
        if idx > 255:
            break
        r, g, b = block[11 + i * 3:14 + i * 3]
        pal[idx * 3:idx * 3 + 3] = [min(63, r) * 255 // 63,
                                    min(63, g) * 255 // 63,
                                    min(63, b) * 255 // 63]
    return pal


def frames(block: bytes):
    """Yield (index, width, height, pixels) per frame, XOR deltas resolved."""
    h = header(block)
    size = h["width"] * h["height"]
    raw = decompress(block[h["data"]:], size * h["image_count"])
    if len(raw) < size:
        return
    base = raw[h["base_image"] * size:(h["base_image"] + 1) * size]
    for i in range(h["image_count"]):
        chunk = raw[i * size:(i + 1) * size]
        if len(chunk) < size:
            break
        if i != h["base_image"]:
            chunk = bytes(a ^ b for a, b in zip(chunk, base))
        yield i, h["width"], h["height"], chunk

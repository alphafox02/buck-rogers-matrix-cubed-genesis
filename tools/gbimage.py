"""
Gold Box VGA image decoder.

Header layout (10 bytes), confirmed against Buck Rogers: Matrix Cubed:

    u8   height          pixels
    u8   width / 8
    u16  x_start         placement hint, in 8-pixel units
    u16  y_start         placement hint, in 8-pixel units
    u16  image_count     frames stored in this block
    u8   color_base      first palette index this block defines
    u8   color_count - 1 number of palette entries defined

    offset 10: color_count VGA entries, 3 bytes each, 6 bits per channel
    ...
    pixel data: image_count frames of width*height bytes, 8bpp linear,
                located at  len(block) - image_count * width * height

The color_base field is the critical one: a block does NOT define all 256
colours. It defines `color_count` entries starting at index `color_base`.
Indices below color_base come from the game's base palette. Ignoring this
renders the image with every colour shifted, which looks like confetti.
"""

BASE_PALETTE_16 = [
    (0x00, 0x00, 0x00), (0x00, 0x00, 0x2a), (0x00, 0x2a, 0x00), (0x00, 0x2a, 0x2a),
    (0x2a, 0x00, 0x00), (0x2a, 0x00, 0x2a), (0x2a, 0x15, 0x00), (0x2a, 0x2a, 0x2a),
    (0x15, 0x15, 0x15), (0x15, 0x15, 0x3f), (0x15, 0x3f, 0x15), (0x15, 0x3f, 0x3f),
    (0x3f, 0x15, 0x15), (0x3f, 0x15, 0x3f), (0x3f, 0x3f, 0x15), (0x3f, 0x3f, 0x3f),
]


def header(block: bytes) -> dict:
    return {
        "height":      block[0],
        "width":       block[1] * 8,
        "x_start":     int.from_bytes(block[2:4], "little") * 8,
        "y_start":     int.from_bytes(block[4:6], "little") * 8,
        "image_count": int.from_bytes(block[6:8], "little"),
        "color_base":  block[8],
        "color_count": block[9] + 1,
    }


def palette(block: bytes) -> list:
    """Return a flat 768-entry RGB list suitable for PIL.putpalette()."""
    h = header(block)
    pal = [0] * 768
    # Seed the low indices with the standard VGA 16-colour set.
    for i, (r, g, b) in enumerate(BASE_PALETTE_16):
        pal[i * 3:i * 3 + 3] = [r * 255 // 63, g * 255 // 63, b * 255 // 63]
    # Overlay the range this block actually defines.
    for i in range(h["color_count"]):
        idx = h["color_base"] + i
        if idx > 255:
            break
        src = 10 + i * 3
        if src + 3 > len(block):
            break
        r, g, b = block[src:src + 3]
        pal[idx * 3:idx * 3 + 3] = [
            min(63, r) * 255 // 63, min(63, g) * 255 // 63, min(63, b) * 255 // 63
        ]
    return pal


def frames(block: bytes):
    """Yield (index, width, height, pixel_bytes) for each frame in the block."""
    h = header(block)
    size = h["width"] * h["height"]
    if size == 0 or h["image_count"] == 0:
        return
    start = len(block) - h["image_count"] * size
    if start < 10:
        return
    for i in range(h["image_count"]):
        off = start + i * size
        yield i, h["width"], h["height"], block[off:off + size]

"""
Build synthetic dungeon maps for unambiguous transplant testing.

Comparing a transplanted dungeon against the original by eye does not work:
both are plausible level design, and nobody has the stock layout memorised.
A synthetic map removes the judgement call -- either the player sees an
obviously artificial layout or the transplant is not reaching the screen.

Maps are the four-plane 16x16 format from docs/formats.md, emitted in the
DOS 1026-byte form (2-byte id header) so they drop straight into the
existing tooling.
"""

import struct

SIZE = 16
N, E, S, W = "N", "E", "S", "W"


def _blank():
    return {d: [[0] * SIZE for _ in range(SIZE)] for d in (N, E, S, W)}


def _emit(walls, info, geo_id=0):
    ne = bytearray(SIZE * SIZE)
    sw = bytearray(SIZE * SIZE)
    inf = bytearray(SIZE * SIZE)
    flags = bytearray(SIZE * SIZE)
    for y in range(SIZE):
        for x in range(SIZE):
            i = y * SIZE + x
            ne[i] = (walls[N][y][x] << 4) | walls[E][y][x]
            sw[i] = (walls[S][y][x] << 4) | walls[W][y][x]
            inf[i] = info[y][x]
    return struct.pack("<H", geo_id) + bytes(ne + sw + inf + flags)


def open_field(wall_type=1):
    """Every interior wall removed; only the outer boundary remains.

    The most binary test available: walk the full width or height and you
    should never be stopped.
    """
    w = _blank()
    for i in range(SIZE):
        w[N][0][i] = wall_type
        w[S][SIZE - 1][i] = wall_type
        w[W][i][0] = wall_type
        w[E][i][SIZE - 1] = wall_type
    return _emit(w, [[1] * SIZE for _ in range(SIZE)])


def checkerboard(wall_type=1):
    """Alternate squares fully enclosed -- a regular grid no designer would draw."""
    w = _blank()
    info = [[1] * SIZE for _ in range(SIZE)]
    for y in range(SIZE):
        for x in range(SIZE):
            if (x + y) % 2:
                w[N][y][x] = w[E][y][x] = w[S][y][x] = w[W][y][x] = wall_type
    return _emit(w, info)


def corridor(wall_type=1):
    """One straight east-west corridor across the middle, everything else solid."""
    w = _blank()
    info = [[0] * SIZE for _ in range(SIZE)]
    mid = SIZE // 2
    for y in range(SIZE):
        for x in range(SIZE):
            if y != mid:
                w[N][y][x] = w[E][y][x] = w[S][y][x] = w[W][y][x] = wall_type
            else:
                w[N][y][x] = w[S][y][x] = wall_type
                info[y][x] = 1
    w[W][mid][0] = wall_type
    w[E][mid][SIZE - 1] = wall_type
    return _emit(w, info)


SHAPES = {"open": open_field, "checker": checkerboard, "corridor": corridor}

if __name__ == "__main__":
    import sys
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import geo
    for name, fn in SHAPES.items():
        m = geo.Map(fn())
        print(f"=== {name} ===")
        print("\n".join(m.render().splitlines()[:7]))
        print()

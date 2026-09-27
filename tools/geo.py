# SPDX-License-Identifier: MIT
"""
Gold Box dungeon map (GEO) decoder.

A map block is 1026 bytes: a 2-byte GEO id followed by four parallel
256-byte planes over a 16x16 grid. Each plane stores one attribute per
square, indexed y * 16 + x:

    plane 0  walls NORTH (high nibble) / EAST (low nibble)
    plane 1  walls SOUTH (high nibble) / WEST (low nibble)
    plane 2  square info -- one byte per square
    plane 3  door flags: WEST bits 7-6, SOUTH 5-4, EAST 3-2, NORTH 1-0

A wall value of 0 means open. Non-zero selects a wall graphic from the
area's wall set (see WALLDEF1.DAX). A square is a door in some direction
when that direction's flag pair is non-zero; the value distinguishes open
from closed.

Structure cross-checked against farmboy0/ssi-engine
(data/dungeon/DungeonMap.java), read as documentation.
"""

import struct

SIZE = 16
PLANE = SIZE * SIZE
HEADER = 2

NORTH, EAST, SOUTH, WEST = "N", "E", "S", "W"


class Square:
    __slots__ = ("walls", "info", "doors")

    def __init__(self, walls, info, doors):
        self.walls, self.info, self.doors = walls, info, doors

    def blocked(self, direction) -> bool:
        """A wall blocks unless it is a door standing open."""
        if not self.walls[direction]:
            return False
        return self.doors[direction] != 1

    def is_door(self, direction) -> bool:
        return self.doors[direction] != 0


class Map:
    def __init__(self, block: bytes):
        if len(block) != HEADER + 4 * PLANE:
            raise ValueError(f"expected {HEADER + 4 * PLANE} bytes, got {len(block)}")
        self.geo_id = struct.unpack_from("<H", block, 0)[0]
        body = block[HEADER:]
        self.squares = []
        for y in range(SIZE):
            row = []
            for x in range(SIZE):
                i = y * SIZE + x
                ne, sw = body[i], body[PLANE + i]
                flags = body[3 * PLANE + i]
                row.append(Square(
                    {NORTH: ne >> 4, EAST: ne & 0xF,
                     SOUTH: sw >> 4, WEST: sw & 0xF},
                    body[2 * PLANE + i],
                    {WEST: (flags >> 6) & 3, SOUTH: (flags >> 4) & 3,
                     EAST: (flags >> 2) & 3, NORTH: flags & 3},
                ))
            self.squares.append(row)

    def at(self, x, y) -> Square:
        return self.squares[y][x]

    def render(self) -> str:
        """ASCII floor plan: walls as lines, doors as + or ', open as space."""
        out = []
        for y in range(SIZE):
            top = mid = ""
            for x in range(SIZE):
                sq = self.at(x, y)
                top += "+" + ("   " if not sq.walls[NORTH]
                              else " + " if sq.is_door(NORTH) else "---")
                mid += ("|" if sq.walls[WEST] and not sq.is_door(WEST)
                        else "'" if sq.is_door(WEST) else " ")
                mid += " . " if sq.info else "   "
            out.append(top + "+")
            out.append(mid + "|")
        # bottom edge
        out.append("".join("+" + ("---" if self.at(x, SIZE - 1).walls[SOUTH] else "   ")
                           for x in range(SIZE)) + "+")
        return "\n".join(out)

    def stats(self):
        walled = sum(1 for row in self.squares for s in row
                     if any(s.walls.values()))
        doors = sum(1 for row in self.squares for s in row
                    if any(s.doors.values()))
        info = sum(1 for row in self.squares for s in row if s.info)
        return walled, doors, info


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import dax
    path = sys.argv[1] if len(sys.argv) > 1 else "dos_game/matrix/GEO1.DAX"
    blocks = dax.load(path)
    print(f"{len(blocks)} maps in {path}\n")
    for bid in sorted(blocks):
        m = Map(blocks[bid])
        w, d, i = m.stats()
        print(f"  map {bid:3d}  geo_id 0x{m.geo_id:04X}  "
              f"{w:3d} squares with walls, {d:3d} with doors, {i:3d} with info")

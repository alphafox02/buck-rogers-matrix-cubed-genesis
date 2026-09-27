# SPDX-License-Identifier: MIT
"""Route through the opening dock using the map the ROM actually carries."""
import struct, sys
from pathlib import Path
sys.path.insert(0, "tools")
import genesis_ecl as E, geo

def load(area=0x11, path="roms/matrix_play.gen"):
    rom = Path(path).read_bytes()
    at = struct.unpack_from(">I", rom, 0x05770)[0]
    raw = E.decompress(rom[at:], limit=0x40000)
    n = struct.unpack_from(">H", raw, 0)[0]
    ids, body = list(raw[2:2 + n]), raw[2 + n:]
    k = ids.index(area)
    return geo.Map(b"\0\0" + body[k * 1024:(k + 1) * 1024])

STEP = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}

def neighbours(m, x, y):
    sq = m.at(x, y)
    for d, (dx, dy) in STEP.items():
        nx, ny = x + dx, y + dy
        if not (0 <= nx < 16 and 0 <= ny < 16):
            continue
        w = sq.walls[{"N": geo.NORTH, "S": geo.SOUTH,
                      "E": geo.EAST, "W": geo.WEST}[d]]
        if w and not sq.is_door({"N": geo.NORTH, "S": geo.SOUTH,
                                 "E": geo.EAST, "W": geo.WEST}[d]):
            continue
        yield d, (nx, ny)

def route(m, start, goal):
    from collections import deque
    seen, q = {start: None}, deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for d, nxt in neighbours(m, *cur):
            if nxt not in seen:
                seen[nxt] = (cur, d)
                q.append(nxt)
    if goal not in seen:
        return None
    out, cur = [], goal
    while seen[cur]:
        cur, d = seen[cur]
        out.append(d)
    return out[::-1]

if __name__ == "__main__":
    m = load()
    for goal in ((3, 5), (4, 2), (11, 4), (3, 15)):
        print(goal, route(m, (0, 2), goal))

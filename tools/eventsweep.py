# SPDX-License-Identifier: MIT
"""
Stand on every event square of an area and report what the game says.

The ECL dispatches map events through one ONGOTO indexed by the square's
own byte, so the script itself says what each square is FOR. This walks a
build to each of those squares under tools/play.py and records whether
anything was printed, which turns "does the level work?" into a table
instead of an afternoon of play.

    python3 tools/eventsweep.py [area] [out_dir]

Squares are reported as the party's own (x, y). A square that prints
nothing is not necessarily broken -- most events are guarded, and a guard
that declines is the script working -- but a square that prints nothing
when its guard should have passed is exactly the failure this is for.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import genesis_ecl as E
import genesis_disasm as G
import geo
import dockmap

GEO_POINTER = 0x05770
# The map-event dispatch is "mask the square byte, then ONGOTO through a
# long target list". Its offset moves with the block, so it is found rather
# than hardcoded: the widest ONGOTO in the block is always this one.
MIN_TARGETS = 8


def expectations(rom: bytes, area: int):
    """[(x, y), event, the first line that square should print]."""
    code = text = None
    for bid, c, t in E.directory(rom):
        if bid == area:
            code, text = E.decompress(c), E.decompress(t)
    if code is None:
        raise SystemExit(f"no ECL block for area 0x{area:02X}")
    table = G.load_opcodes()
    found = G.disassemble(code, table)
    wide = [o for o, i in found.items()
            if i.name == "ONGOTO" and len(i.args) >= MIN_TARGETS]
    if not wide:
        return []
    disp = max(wide, key=lambda o: len(found[o].args))
    # args[0] of the dispatch is the selector VARIABLE, not a target.
    tgts = [a.value - G.CODE_BASE for a in found[disp].args
            if a.kind == "mem"][1:]
    order = sorted(found)

    def first_text(off):
        if off not in order:
            return "(not decoded)"
        i = order.index(off)
        for q in order[i:i + 16]:
            r = found[q].render(text)
            if found[q].name in ("PRINTCLEAR", "PRINT") and '"' in r:
                return r.split('"')[1]
        return "(" + " ".join(found[q].name for q in order[i:i + 4]) + ")"

    at = struct.unpack_from(">I", rom, GEO_POINTER)[0]
    raw = E.decompress(rom[at:], limit=0x40000)
    n = struct.unpack_from(">H", raw, 0)[0]
    ids, body = list(raw[2:2 + n]), raw[2 + n:]
    k = ids.index(area)
    m = geo.Map(b"\0\0" + body[k * 1024:(k + 1) * 1024])
    out = []
    for x in range(16):
        for y in range(16):
            ev = m.at(x, y).info & 0x3F
            if ev and ev < len(tgts):
                out.append(((x, y), ev, first_text(tgts[ev])))
    return sorted(out)


if __name__ == "__main__":
    area = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x11
    rom = (Path(__file__).resolve().parent.parent / "roms/matrix_play.gen").read_bytes()
    for (x, y), ev, what in expectations(rom, area):
        print(f"  ({x:2d},{y:2d})  event {ev:2d}  {what[:70]}")

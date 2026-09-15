#!/usr/bin/env python3
"""
Build the playable ROM.

The transplant list had been living in shell history, which is no way to
keep a build. This is the whole recipe.

    python3 tools/build.py [out.gen]

Area ids follow the DOS block numbers, in hex -- a convention the exit
graph confirms, since every NEWECL target across all 33 blocks resolves to
a block that exists under it.

Three blocks need spelling out:

  block 1  -> area 0x00   Countdown's boot block and Matrix Cubed's block 1
                          are direct counterparts: both open with "DO YOU
                          WANT TO START FROM SCRATCH OR USE THE JUMPER?".
                          Replacing it outright is what makes the game
                          start in Matrix Cubed rather than falling into
                          Countdown's travel menu.
  block 2  -> area 0x02   SSI's combat test room, which block 1 exits to.
  maps 1, 51, 52          geometry with no script of its own. LOADFILES
                          names a map id, and areas 0x31 and 0x32 load
                          0x34 and 0x33 as sub-levels of their region.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import dax

STOCK = REPO / "roms/countdown.gen"
DEFAULT_OUT = REPO / "roms/matrix_play.gen"

# Transplanted as <area>:<block>[:<map>]; a block of `-` is map-only.
MAP_ONLY = ["0x01:-:1", "0x33:-:51", "0x34:-:52"]


def specs():
    blocks = dax.load(REPO / "dos_game/matrix/ECL1.DAX")
    maps = dax.load(REPO / "dos_game/matrix/GEO1.DAX")
    out = []
    for b in sorted(blocks):
        if b == 1:
            # Block 1's script goes to area 0x00, but its map does not: the
            # block does LOADFILES 1, which names map id 1, so the geometry
            # belongs at geo area 0x01 and is listed in MAP_ONLY. Attaching
            # it here as well would duplicate it and spend one of the
            # engine's 32 geo slots for nothing.
            out.append("0x00:1")
            continue
        out.append(f"0x{b:02X}:{b}" + (f":{b}" if b in maps else ""))
    return out + MAP_ONLY


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    cmd = [sys.executable, str(REPO / "tools/inject_area.py"), str(STOCK), str(out)] + specs()
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

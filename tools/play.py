"""
Drive the built ROM programmatically: press buttons, read RAM, see frames.

Screenshots from a person are the only ground truth this project has had for
anything interactive, which makes every question cost a round trip. This runs
the same ROM under a scriptable Genesis core, so a question like "is that
door passable?" can be answered by walking into it and reading the
coordinates back out of RAM.

    from play import Game
    g = Game("roms/matrix_play.gen")
    g.to_dungeon()                 # through the logos, menus and briefing
    print(g.pos())                 # (x, y, facing)
    g.walk("E")                    # and see whether x changed

RAM that matters, from docs/re_notes.md:

    0xFF9AF7  DUNGEON_X      0xFF9AF6  DUNGEON_Y      0xFF9AFA  facing
    0xFF97E8  the current area

Facing is N, E, S, W for 0..3 in both engines.
"""

import os
import sys
from pathlib import Path

import numpy as np
import stable_retro as retro

REPO = Path(__file__).resolve().parent.parent
INTEGRATION = Path(retro.data.path()) / "stable" / "MatrixCubed-Genesis"

# gym-retro's Genesis button order.
BUTTONS = ["B", "A", "MODE", "START", "UP", "DOWN", "LEFT", "RIGHT",
           "C", "Y", "X", "Z"]

RAM = {"y": 0xFF9AF6, "x": 0xFF9AF7, "dir": 0xFF9AFA, "area": 0xFF97E8}
FACING = {0: "N", 1: "E", 2: "S", 3: "W"}
TURN = {"N": 0, "E": 1, "S": 2, "W": 3}


class Game:
    def __init__(self, rom=REPO / "roms/matrix_play.gen"):
        INTEGRATION.mkdir(parents=True, exist_ok=True)
        import json
        import shutil
        shutil.copy(rom, INTEGRATION / "rom.md")
        json.dump({"info": {k: {"address": v, "type": "|u1"}
                            for k, v in RAM.items()}},
                  open(INTEGRATION / "data.json", "w"))
        self.em = retro.RetroEmulator(str(INTEGRATION / "rom.md"))
        self.gd = retro.data.GameData()
        self.gd.load(str(INTEGRATION / "data.json"))
        self.em.configure_data(self.gd)
        self._none = np.zeros(16, dtype=np.uint8)

    def _mask(self, *names):
        m = self._none.copy()
        for n in names:
            m[BUTTONS.index(n)] = 1
        return m

    def run(self, frames, *buttons):
        m = self._mask(*buttons) if buttons else self._none
        for _ in range(frames):
            self.em.set_button_mask(m)
            self.em.step()

    def tap(self, button, hold=4, rest=10):
        self.run(hold, button)
        self.run(rest)

    def read(self):
        self.gd.update_ram()
        return self.gd.lookup_all()

    def pos(self):
        v = self.read()
        return v["x"], v["y"], FACING.get(v["dir"], v["dir"])

    def frame(self):
        from PIL import Image
        return Image.fromarray(np.asarray(self.em.get_screen()))

    def lit(self):
        """How much of the screen is not black -- a cheap 'is anything drawn'."""
        return int((np.asarray(self.em.get_screen()).sum(axis=2) > 30).sum())

    def face(self, want):
        """Turn on the spot until facing `want` ('N'/'E'/'S'/'W')."""
        for _ in range(4):
            if self.pos()[2] == want:
                return True
            self.tap("RIGHT")
        return self.pos()[2] == want

    def walk(self, direction, steps=1):
        """Face a direction and step. Returns the squares actually moved."""
        before = self.pos()[:2]
        self.face(direction)
        for _ in range(steps):
            self.tap("UP")
        after = self.pos()[:2]
        return abs(after[0] - before[0]) + abs(after[1] - before[1])

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

    def save(self):
        """Snapshot the machine. One emulator per process, so experiments
        rewind to a state rather than rebooting."""
        return self.em.get_state()

    def load(self, state):
        self.em.set_state(state)

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

    def text(self):
        """What the screen says, read off the window plane's tilemap."""
        import genread
        return genread.text(bytes(self.save()))

    def options(self):
        """[(option, selected)] for the menu on the bottom line, if any."""
        import genread
        return genread.choices(bytes(self.save()))

    def pick(self, want, tries=12):
        """Move the cursor onto `want` on the bottom line and press C."""
        want = want.upper()
        for _ in range(tries):
            opts = self.options()
            names = [w for w, _ in opts]
            if want not in names:
                return False
            here = [i for i, (_w, sel) in enumerate(opts) if sel]
            if not here:
                self.tap("RIGHT", hold=8, rest=40)
                continue
            i, j = here[0], names.index(want)
            if i == j:
                self.tap("C", hold=10, rest=130)
                return True
            # Step towards it rather than the short way round: the cursor
            # does not always wrap, and a wrap that does not happen leaves
            # the picker pressing LEFT at the first option forever.
            self.tap("RIGHT" if j > i else "LEFT", hold=8, rest=40)
        return False

    def lit(self):
        """How much of the screen is not black -- a cheap 'is anything drawn'."""
        return int((np.asarray(self.em.get_screen()).sum(axis=2) > 30).sum())

    MENU_LIT = (21000, 24000)

    def to_menu(self, limit=14):
        """
        Boot as far as the main menu and stop there.

        The intro is a fixed sequence -- EA logo, Buck Rogers logo, the
        Matrix Cubed card, then the menu -- and each screen waits for a
        button. Pressing one time too many SELECTS the highlighted item and
        drops into character creation, which is what made the first attempts
        at this look like the menu was ignoring input. So it presses until
        the screen matches the menu's brightness and then stops.
        """
        self.run(420)
        for _ in range(limit):
            if self.MENU_LIT[0] <= self.lit() <= self.MENU_LIT[1]:
                return True
            self.tap("C", hold=8, rest=60)
        return self.MENU_LIT[0] <= self.lit() <= self.MENU_LIT[1]

    # Main menu icons, left to right.
    MENU = ("create", "drop", "save", "restore", "begin")

    def menu_pick(self, which):
        self.to_menu()
        for _ in range(self.MENU.index(which)):
            self.tap("RIGHT", hold=8, rest=40)
        self.tap("C", hold=8, rest=120)

    def face(self, want):
        """Turn on the spot until facing `want` ('N'/'E'/'S'/'W')."""
        for _ in range(4):
            if self.pos()[2] == want:
                return True
            self.tap("RIGHT")
        return self.pos()[2] == want

    def to_party(self):
        """
        Boot, load the pregenerated team, and play the opening.

        There is a save in slot 1 called PREGENERATED TEAM -- Flavius,
        Celeste, Pierre, Nichole, Romare and Janelle, already equipped -- so
        the party does not have to be created a character at a time.

        This reaches the start square and the whole opening plays: the space
        cutscene, Buck Rogers in the window with his four speeches, the
        starting kit handed over as "THE TEAM HAS FOUND 8000 CREDITS", and
        the character sheet.

        It stops there. The equipment screens nest several deep and exiting
        them by button search did not come out the other side; getting to
        free movement is unfinished. What this IS good for is confirming the
        party lands on the right square facing the right way, which is how
        the crossed DUNGEON_X/DUNGEON_Y was verified without a person
        watching: it reads (0, 2, 'E'), exactly what the DOS status line
        shows at the opening.
        """
        self.menu_pick("restore")
        self.tap("C", hold=8, rest=80)      # slot 1, the pregenerated team
        self.tap("C", hold=8, rest=80)      # its roster
        self.tap("RIGHT", hold=8, rest=40)  # restore -> begin adventure
        self.tap("C", hold=8, rest=120)
        for _ in range(16):                 # the briefing and the kit
            self.tap("C", hold=8, rest=70)
        return self.pos()

    # The d-pad moves in ABSOLUTE directions -- UP walks north and turns the
    # party to face north -- rather than forward/turn as the DOS game does.
    # Getting that wrong is what made the first movement tests look like the
    # party was frozen: they turned with RIGHT and then pressed UP, which
    # just walked north every time.
    PAD = {"N": "UP", "S": "DOWN", "W": "LEFT", "E": "RIGHT"}

    def walk(self, direction, steps=1):
        """Step in a compass direction. Returns the squares actually moved."""
        before = self.pos()[:2]
        for _ in range(steps):
            # Generous timing on purpose. At hold=10/rest=90 roughly a third
            # of steps were silently dropped, which reads exactly like a wall
            # and made the map look wrong when it was not.
            self.tap(self.PAD[direction], hold=14, rest=150)
        after = self.pos()[:2]
        return abs(after[0] - before[0]) + abs(after[1] - before[1])

    def clear(self, tries=4):
        """
        Dismiss whatever is waiting for a button.

        Walking around fires events: a line of text to page through, a
        question to answer, sometimes a fight. While one is up the pad does
        not move the party, which reads exactly like a wall and made the map
        look wrong when it was not. So a step that fails is followed by a few
        presses and tried again before it is believed.
        """
        for _ in range(tries):
            self.tap("C", hold=10, rest=70)

    def step(self, direction):
        """Move one square, pushing through anything that interrupts."""
        if self.walk(direction):
            return True
        self.clear()
        return bool(self.walk(direction))

    def to_dungeon(self):
        """
        Boot all the way to free movement on the opening dock.

        Load the pregenerated team, begin, sit through the briefing, then get
        out of the spoils screen -- which is the fiddly part. Its EXIT asks
        "THERE IS STILL BOOTY LEFT. GO BACK AND CLAIM IT?" and the answer has
        to be NO, or it puts you straight back in.
        """
        self.to_party()
        for _ in range(3):
            self.tap("DOWN", hold=8, rest=25)
        self.tap("RIGHT", hold=8, rest=25)
        self.tap("C", hold=8, rest=110)         # character sheet
        self.tap("C", hold=8, rest=110)         # the spoils screen
        for _ in range(3):
            self.tap("DOWN", hold=8, rest=30)   # down to EXIT
        self.tap("START", hold=10, rest=140)    # -> the booty prompt
        self.tap("RIGHT", hold=10, rest=90)     # -> NO
        self.tap("C", hold=10, rest=200)
        for _ in range(6):                      # arrival text, the chancellor
            self.tap("C", hold=10, rest=140)
        return self.pos()

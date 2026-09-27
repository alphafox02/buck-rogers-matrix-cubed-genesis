# SPDX-License-Identifier: MIT
"""
Walk into one transplanted area and write down everything it says.

Comparing the port with the original means knowing what each area actually
does, and until now that meant a person playing it. With the screen
readable (genread) and the menus answerable (play.Game.pick) an area can
introduce itself: boot straight into it with visit.py, then keep clearing
whatever is on screen and record each new thing said.

It answers a prompt the way a cautious player would -- NO, EXIT, LEAVE --
so a sweep does not buy drinks in every bar it finds or walk into a fight
it cannot win, and it stops as soon as the area stops saying anything new.

Usage:
    tour.py <area_id> [steps]
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Answers that decline, in the order they are preferred.
DECLINE = ("EXIT", "LEAVE", "NO", "NOTHING", "DONE", "IGNORE HIM",
           "MOVE AWAY", "HIDE", "FLEE", "WAIT")
# Compass moves, tried in turn once the talking stops.
WALK = ("N", "E", "S", "W")


def build(area, rom=None):
    """A ROM that boots into `area`, built into a temporary file."""
    rom = rom or REPO / "roms/matrix_play.gen"
    out = Path(tempfile.gettempdir()) / f"tour_{area:02X}.gen"
    subprocess.run([sys.executable, str(REPO / "tools/visit.py"),
                    str(rom), str(out), hex(area)],
                   check=True, stdout=subprocess.DEVNULL)
    return out


def tour(area, steps=40, rom=None):
    """[(what the screen said, the options it offered)] for one area."""
    import play
    g = play.Game(build(area, rom))
    g.to_dungeon()
    seen, log = set(), []
    for _ in range(steps):
        text = g.text().strip()
        body = "\n".join(l.strip() for l in text.splitlines() if l.strip())
        opts = g.options()
        if body and body not in seen:
            seen.add(body)
            log.append((body, [w for w, _ in opts]))
        names = [w for w, _ in opts]
        for want in DECLINE:
            if want in names:
                g.pick(want)
                break
        else:
            if len(names) > 1:
                g.tap("C", hold=10, rest=130)
            elif not any(g.walk(d) for d in WALK):
                g.tap("C", hold=10, rest=130)
    return g, log


if __name__ == "__main__":
    area = int(sys.argv[1], 0)
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    g, log = tour(area, steps)
    print(f"=== area 0x{area:02X}  ({len(log)} screens)")
    for body, opts in log:
        for line in body.splitlines():
            print("   ", line)
        if opts:
            print("      [", " | ".join(opts), "]")
    print("   final position", g.pos(), "area 0x%02X" % g.read()["area"])

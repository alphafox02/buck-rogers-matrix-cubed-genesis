"""The game's level graph, read out of the DOS scripts.

Each ECL block is one place, and NEW_ECL is the door between them. Printing
the graph answers the question that matters while porting: what is supposed
to come next, and which places has nothing been checked in yet.

Block 19 is the hub -- Salvation's star map -- and reaches ten others
directly. The opening dock, block 17, has exactly one exit, to 18.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "extracted/ecl/ECL1"

# The first substantial line of a block is usually the place introducing
# itself, which makes a serviceable name without a hand-written table.
FIRST = re.compile(r'PRINT(?:_CLEAR)?\s+"([^"]{20,110})"')
EXIT = re.compile(r"NEW_ECL\s+(\d+)")


def graph(src=None):
    """{block: (name, [blocks it leads to])}"""
    out = {}
    for f in sorted((src or SRC).glob("*.ecl")):
        text = f.read_text(errors="replace")
        m = FIRST.search(text)
        out[int(f.stem)] = (m.group(1) if m else "",
                            sorted({int(e) for e in EXIT.findall(text)}))
    return out


def unreachable(g, start=17):
    """Blocks no chain of NEW_ECL reaches from the opening dock."""
    seen, queue = {start}, [start]
    while queue:
        for nxt in g.get(queue.pop(), ("", []))[1]:
            if nxt not in seen and nxt in g:
                seen.add(nxt); queue.append(nxt)
    return sorted(set(g) - seen)


if __name__ == "__main__":
    g = graph()
    for block, (name, exits) in sorted(g.items()):
        leads = ", ".join(str(e) for e in exits) or "-"
        print(f"  {block:3d} -> {leads:28s} {name[:60]}")
    print("\nnot reached from the dock:", unreachable(g))

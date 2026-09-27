# SPDX-License-Identifier: MIT
"""
Find text that still overflows the Genesis window, in a built ROM.

The window is 35 columns by 4 lines and the engine does not clip: a fifth
line lands back on the first, so the player reads the end of a speech written
over the top of its beginning. `transpile.py` simulates the window and inserts
page breaks, but a simulation is only as good as its model of the engine, and
the bug it missed for months -- conditionals ending the run -- was found by a
person reading a screenshot, not by the build.

So this checks the output instead of trusting the input. It walks the
disassembled scripts of a built ROM and replays each run of prints the way the
window does, reporting any page that does not fit.

It is deliberately independent of the transpiler: if both agreed by sharing
code, agreement would prove nothing.

Usage:
    textcheck.py <disassembly dir>
"""

import re
import sys
from pathlib import Path

COLUMNS, LINES = 35, 4
VARIABLE = 12                 # budget for a name printed from a variable

# Instructions the window does not notice. RETURN, EXIT and GOTO are NOT
# here: a RETURN between two prints means they are alternative branches of a
# subroutine and only one of them runs, so counting both is how a checker
# invents overflows that are not there.
TRANSPARENT = {
    "AND", "OR", "COMPARE", "ADD", "SUB", "SAVE", "IFEQ", "IFNE", "IFLT",
    "IFGT", "IFLE", "IFGE", "GOSUB", "SOUND", "DELAY", "CONTINUE",
}
STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def wrap(text):
    out, cur = [], ""
    for word in text.split(" "):
        if cur and len(cur) + 1 + len(word) > COLUMNS:
            out.append(cur)
            cur = word
        else:
            cur = (cur + " " + word) if cur else word
    if cur:
        out.append(cur)
    return out or [""]


def text_of(line):
    m = STR_RE.search(line)
    if m:
        return m.group(1)
    if "str[" in line or "[0x" in line:
        return "x" * VARIABLE
    return None


def check(path):
    """Replay each run of prints, tracking the cursor the way the window does."""
    bad = []
    line = col = 0
    start = None
    shown = []

    def place(text):
        """Advance the cursor over `text`, returning the rows it occupies."""
        nonlocal line, col
        rows = wrap((" " * col) + text) if col else wrap(text)
        if col:
            rows[0] = rows[0][col:]
        line += len(rows) - 1
        col = len(rows[-1])
        return rows

    for raw in path.read_text().splitlines():
        parts = raw.split(None, 2)
        if len(parts) < 2:
            continue
        off, name = parts[0], parts[1]
        rest = parts[2] if len(parts) > 2 else ""
        if name == "PRINTCLEAR":
            line = col = 0
            start, shown = off, []
            shown += place(text_of(rest) or "")
        elif start is None:
            continue
        elif name == "PRINT":
            shown += place(text_of(rest) or "")
        elif name == "PRINTRETURN":
            line += 1
            col = 0
            shown.append("")
        elif name in TRANSPARENT:
            continue
        else:
            start = None
            continue
        if start is not None and line >= LINES:
            bad.append((start, line + 1, shown))
            start = None
    return bad


if __name__ == "__main__":
    d = Path(sys.argv[1] if len(sys.argv) > 1 else "extracted/genesis_ecl_disasm")
    total = 0
    for f in sorted(d.glob("*.ecl")):
        for off, n, rows in check(f):
            total += 1
            print(f"{f.stem} {off}: {n} lines")
            for i, row in enumerate(rows):
                print(f"      {'>>' if i >= LINES else '  '} {row}")
    print(f"\n{total} pages overflow the {COLUMNS}x{LINES} window")

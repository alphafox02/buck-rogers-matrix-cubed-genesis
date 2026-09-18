"""
Catch two things writing to the same place in the ROM.

Every injector allocates from a base address it picked when it was written,
and those bases were chosen against whatever else existed at the time. As
more art goes in, a region grows past the next one's base and the later step
silently overwrites the earlier one. Nothing errors -- the ROM is valid, the
checksum is repaired, the game boots -- and the only symptom is a picture
that does not appear.

That has now happened three times:

  * the figure directory relocated into the monster stream
  * the monster stream written in place over live data
  * the title art at 0x1F8000 over portraits 0x6A and 0x6B, which is why
    the shopkeeper's face was missing and the default space view showed
    instead

So this reads the build's own output -- every step already prints where it
wrote and how much -- and fails the build if two ranges intersect.

Usage:
    build.py ... | romlayout.py          # reads a build log on stdin
    romlayout.py <log>
"""

import re
import sys
from pathlib import Path

# Each pattern yields (start, length, label). Every injector already prints
# what it wrote; these just read it back.
PATTERNS = (
    (r"picture (0x[0-9A-Fa-f]+): .*?-> (\d+) packed at (0x[0-9A-F]+)",
     lambda m: (int(m[3], 16), int(m[2]), f"picture {m[1]}")),
    (r"^  (\w+): .*?-> (\d+) packed at (0x[0-9A-F]+)",
     lambda m: (int(m[3], 16), int(m[2]), f"title/{m[1]}")),
    (r"figure (0x[0-9A-F]+) <- .*?, (\d+) bytes at (0x[0-9A-F]+)",
     lambda m: (int(m[3], 16), int(m[2]), f"creature {m[1]}")),
    (r"stream (\d+) bytes at (0x[0-9A-F]+)",
     lambda m: (int(m[2], 16), int(m[1]), "monster stream")),
    (r"(\d+) records at (0x[0-9A-F]+)",
     lambda m: (int(m[2], 16), int(m[1]) * 8, "figure directory")),
    (r"music\[\d+\] .*? at (0x[0-9A-F]+), ends (0x[0-9A-F]+)",
     lambda m: (int(m[1], 16), int(m[2], 16) - int(m[1], 16), "music")),
    (r"(\w[\w ]*?), (\d+) bytes\s*$",
     None),          # unused; kept so the shape of this table is obvious
)


def spans(log):
    out = []
    for pattern, build in PATTERNS:
        if build is None:
            continue
        for m in re.finditer(pattern, log, re.M):
            out.append(build([m.group(0)] + list(m.groups())))
    return sorted(out)


def overlaps(items):
    bad = []
    for i, (a, n, what) in enumerate(items):
        for b, m, other in items[i + 1:]:
            if b >= a + n:
                break
            if what == other:
                continue
            bad.append((a, n, what, b, m, other))
    return bad


def main_from_text(log):
    """Check a build transcript. Returns non-zero if anything overlaps."""
    items = spans(log)
    if not items:
        print("  romlayout: nothing to check")
        return 0
    bad = overlaps(items)
    lo, hi = items[0][0], max(a + n for a, n, _ in items)
    print(f"  romlayout: {len(items)} written regions, 0x{lo:06X}-0x{hi:06X}, "
          f"{'NO overlaps' if not bad else str(len(bad)) + ' OVERLAP(S)'}")
    for a, n, what, b, m, other in bad:
        print(f"    0x{a:06X}+{n} ({what}) overlaps 0x{b:06X}+{m} ({other}) "
              f"-- whichever runs later wins and the other is lost")
    return 1 if bad else 0


def main():
    return main_from_text(
        Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read())


if __name__ == "__main__":
    sys.exit(main())

"""Answer Matrix Cubed's DOS copy-protection question.

Starting an adventure asks a manual lookup -- "in the log book on page 44,
following the heading THE CAPTAIN SPEAKS, what is the sixth word?" -- and
without the printed log book the game cannot be driven at all.

START.EXE carries both halves of every question, lightly obfuscated, in a
table around 0x0E200. A record is

    slot  key  key  text, reversed, with the key added to every byte

so it decodes by reversing and subtracting. Storing the key twice is what
makes records findable without following the allocator chain they are strung
on, which changes shape partway through the table.

Records alternate: a heading whose slot is the log book page, then its
answer whose slot is the ordinal. Page 44's THE CAPTAIN SPEAKS is followed
by slot 6, THROAT -- the sixth word, and the game accepted it.
"""

import re
from pathlib import Path

EXE = Path(__file__).resolve().parent.parent / "dos_game/matrix/START.EXE"
TABLE = (0x0E200, 0x0E6E0)

# The log book runs from page 32 to page 50; an answer is one of the first
# ten words of its passage. The two ranges do not overlap, which is how a
# record says which kind it is.
PAGES = range(30, 60)
ORDINALS = range(1, 11)
WORD = re.compile(r"[A-Z][A-Z' .-]{2,23}")

NAMES = ["", "first", "second", "third", "fourth", "fifth", "sixth",
         "seventh", "eighth", "ninth", "tenth"]


def records(exe=None):
    """Every record in the table, in file order, as (slot, text)."""
    data = (exe or EXE).read_bytes()
    lo, hi = TABLE
    out, i = [], lo
    while i < hi:
        slot, key = data[i], data[i + 1]
        if data[i + 2] != key or not 1 <= key < 64:
            i += 1
            continue
        # The text runs until a byte that does not decode to a letter.
        j = i + 3
        while j < hi and chr((data[j] - key) & 0xFF) in \
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ' .-":
            j += 1
        text = bytes((c - key) & 0xFF for c in data[i + 3:j][::-1]).decode()
        if WORD.fullmatch(text) and (slot in PAGES or slot in ORDINALS):
            out.append((slot, text))
            i = j
            continue
        i += 1
    return out


def answers(exe=None):
    """{(page, heading): (ordinal, word)} for every question the game asks."""
    r = records(exe)
    out = {}
    for (slot, text), (nxt, word) in zip(r, r[1:]):
        if slot in PAGES and nxt in ORDINALS:
            out[(slot, text)] = (nxt, word)
    return out


def lookup(page, heading="", exe=None):
    """The answer word for one question, or None."""
    want = re.sub(r"[^A-Z]", "", heading.upper())
    for (p, h), (ordinal, word) in answers(exe).items():
        if p == page and want in re.sub(r"[^A-Z]", "", h):
            return h, ordinal, word
    return None


if __name__ == "__main__":
    for (page, heading), (ordinal, word) in sorted(answers().items()):
        print(f"  page {page}  {heading:24s} {NAMES[ordinal]:8s} -> {word}")

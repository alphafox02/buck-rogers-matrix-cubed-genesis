# SPDX-License-Identifier: MIT
"""
Check the two games are present and are the right dumps, before building.

This repository contains no game data. It is tooling and reverse-engineering
notes: everything it needs is read out of copies of the two originals that
whoever runs it already owns. So the first thing a build should do is say
plainly whether those copies are there and whether they are the ones the
tools were written against.

A wrong dump is worse than a missing one. Matrix Cubed shipped in several
releases and Countdown has at least one alternate Genesis revision; the
offsets throughout `tools/` were measured against the ones below, and a
different dump will produce a ROM that builds cleanly and behaves oddly.

A mismatch is a warning rather than an error. Another revision may well
work, and refusing to try would be worse than saying so.

Usage:
    checkinputs.py
"""

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Everything the build reads, and the dump each tool was measured against.
REQUIRED = {
    "roms/countdown.gen":         "89c39f00745f2a8798fe985ad8ce28411b977f9e",
    "dos_game/matrix/ECL1.DAX":   "0d8f4b3965585de0c616a3877cf1036b84014b1b",
    "dos_game/matrix/GEO1.DAX":   "aec4b17fbe97a20e3f281f47611c4e52516a02a8",
    "dos_game/matrix/PIC1.DAX":   "b7348b9b322a651a742b2e13871dfd43b62ad3c4",
    "dos_game/matrix/BIGPIC1.DAX": "010af92c8b9d677bfb3f583d66a06e0e68c32056",
    "dos_game/matrix/TITLE.DAX":  "0186762674286761069a5f37a690633bc1c416a3",
    "dos_game/matrix/MON0CHA.DAX": "220745852dd7cbb15df6185e72c7685c3e915a93",
    "dos_game/matrix/ITEM0.DAX":  "22bdd6c3fc99d61bca0fbd641dd006558baa18bb",
    "dos_game/matrix/BUCKA.XMI":  "092f62c9a63d07e03c995f774c780a3bb1c0fe5a",
}

# Read by some tools but not by a default build.
OPTIONAL = ("dos_game/matrix/SPRIT1.DAX", "dos_game/matrix/PIC8.DAX",
            "dos_game/matrix/CPIC1.DAX", "dos_game/matrix/COMSPR.DAX",
            "dos_game/matrix/WALLDEF1.DAX", "dos_game/matrix/START.EXE",
            "dos_game/matrix/GAME.OVR")


def sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def rescue(rel):
    """Look for a missing input somewhere else and say where it is.

    Getting the layout right is the one genuine obstacle to building this,
    and it is not obvious from a bare "file not found". A DOS installation
    can arrive as an archive, in a directory of another name, or with its
    filenames lowercased by whatever unpacked it -- all of which are easy to
    fix once somebody says which of the three happened.
    """
    want = Path(rel).name
    hits = []
    for found in REPO.rglob("*"):
        if not found.is_file() or found.name.upper() != want.upper():
            continue
        if ".git" in found.parts:
            continue
        hits.append(found)
        if len(hits) >= 3:
            break
    return hits


def archives():
    """Archives in the repository that hold the DOS game, and their prefix."""
    import zipfile
    out = []
    for z in sorted(REPO.glob("*.zip")):
        try:
            with zipfile.ZipFile(z) as zf:
                names = zf.namelist()
        except Exception:
            continue
        dax = [n for n in names if n.upper().endswith("ECL1.DAX")]
        if dax:
            out.append((z, dax[0].rsplit("/", 1)[0] if "/" in dax[0] else ""))
    return out


def check(verbose=True):
    missing, wrong = [], []
    for rel, want in REQUIRED.items():
        p = REPO / rel
        if not p.exists():
            missing.append(rel)
            continue
        if sha1(p) != want:
            wrong.append(rel)
    if verbose:
        for rel in missing:
            print(f"  MISSING   {rel}")
        for rel in wrong:
            print(f"  different dump: {rel}\n"
                  f"            have {sha1(REPO / rel)}\n"
                  f"            want {REQUIRED[rel]}")
        absent = [o for o in OPTIONAL if not (REPO / o).exists()]
        if absent:
            print(f"  optional, not present: {', '.join(absent)}")
        if not missing and not wrong:
            print(f"  all {len(REQUIRED)} required files present and matching")
    return missing, wrong


if __name__ == "__main__":
    missing, wrong = check()
    if missing:
        print("\nThis repository ships no game data. Provide your own copies:\n"
              "    roms/countdown.gen        a Countdown to Doomsday cartridge dump\n"
              "    dos_game/matrix/          a Matrix Cubed DOS installation\n")
        # Say where the files actually are, if they are anywhere.
        helped = False
        for rel in missing:
            for found in rescue(rel):
                print(f"  {Path(rel).name} looks like it is already here:\n"
                      f"      {found.relative_to(REPO)}\n"
                      f"      wanted at {rel}")
                helped = True
        for z, prefix in archives():
            inner = f"{prefix}/" if prefix else ""
            print(f"  {z.name} contains the DOS game under {inner or '(no prefix)'}\n"
                  f"      unzip '{z.name}' -d dos_game/"
                  + ("" if prefix == "matrix" else
                     f"\n      then arrange it so the .DAX files sit in dos_game/matrix/"))
            helped = True
        if not helped:
            print("  Nothing resembling either game was found in this directory.")
        print("\nThen run this again.")
        sys.exit(1)
    if wrong:
        print("\nBuilding anyway. Every offset in tools/ was measured against\n"
              "the dumps listed above; a different revision may still work.")
    sys.exit(0)

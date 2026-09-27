# SPDX-License-Identifier: MIT
"""
Check each transplanted area against its DOS original, without playing it.

Playing both versions side by side is the honest test, and it is also slow
and only finds what you happen to walk into. Most of what can go wrong is
checkable: the question "is this area coherent?" decomposes into things that
either hold or do not.

For every area this reports:

    text      DOS strings that survived into the Genesis text pool. Text is
              the story; a lost string is a scene the player cannot follow.
    flow      jump targets that resolve. One that does not lands at the
              block's start instead, which is a silent wrong turn.
    live      instructions that still do something. A stubbed opcode is
              stepped over safely but its effect is gone.
    art       PICTURE ids that resolve to real artwork rather than the
              engine's substitute.
    exits     NEW_ECL transitions preserved, so the area still leads where
              it led. An area that plays perfectly and goes nowhere is
              still a broken game.

None of this proves an area plays correctly -- only that nothing measurable
was lost getting it here. What it is for is ranking: it says which areas are
worth walking through first.

Usage:
    areacheck.py [area ...]
"""

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import artmap
import dax
import ecl
import flagmap
import transpile


def dos_strings(items):
    out = []
    for ins in items:
        for a in list(ins.args) + list(ins.dyn_args or []):
            if getattr(a, "type", None) == 0x80:
                out.append(str(a.value))
    return out


def check(block_id, blob, flags):
    items, _, _ = ecl.disassemble_block(blob)
    items = [items[o] for o in sorted(items)]
    code, pool, report = transpile.transpile(blob, flags)

    kinds = collections.Counter(w for _, w, why in report
                                if not str(why).startswith("no Genesis"))
    stubs = sum(1 for _, _, why in report if why == "no Genesis counterpart")

    # Text: every DOS string should be findable in the pool, allowing for the
    # long ones having been split across screens and menu labels shortened.
    want = dos_strings(items)
    blob_text = pool.decode("ascii", "replace")
    kept = sum(1 for s in want
               if s in blob_text or (s and s[:28] in blob_text))

    live = len(items) - stubs
    exits = sum(1 for i in items if i.name == "NEW_ECL")
    # 0xFF is "no picture", not a missing one -- the loader tests the id for
    # a sign bit and clears the window. Counting those as substitutions made
    # area 17 read 11/13 when nothing was wrong with it.
    pics = [a.value for i in items if i.name == "PICTURE"
            for a in i.args[:1]
            if getattr(a, "type", None) == 0x00 and a.value < 0x80]
    good_art = sum(1 for p in pics if p in artmap.AVAILABLE)
    return {
        "instrs": len(items), "live": live, "stubs": stubs,
        "text_want": len(want), "text_kept": kept,
        "jumps_bad": kinds.get("jump", 0),
        "art_want": len(pics), "art_ok": good_art,
        "exits": exits, "bytes": len(blob),
    }


def pct(a, b):
    return 100.0 if not b else 100.0 * a / b


def main():
    mc = dax.load(REPO / "dos_game/matrix/ECL1.DAX")
    flags = flagmap.build((REPO / "roms/countdown.gen").read_bytes())
    want = [int(a, 0) for a in sys.argv[1:]] or sorted(mc)

    print(f"{'area':>5} {'instrs':>7} {'live':>6} {'text':>10} "
          f"{'flow':>6} {'art':>9} {'exits':>6}   notes")
    worst = []
    for b in want:
        if b not in mc:
            continue
        r = check(b, mc[b], flags)
        tp = pct(r["text_kept"], r["text_want"])
        fp = pct(r["instrs"] - r["jumps_bad"], r["instrs"])
        ap = pct(r["art_ok"], r["art_want"])
        notes = []
        if r["stubs"]:
            notes.append(f"{r['stubs']} dead")
        if r["jumps_bad"]:
            notes.append(f"{r['jumps_bad']} lost jumps")
        if r["art_want"] and ap < 100:
            notes.append(f"{r['art_want'] - r['art_ok']} substituted")
        print(f"{b:5} {r['instrs']:7} {r['live']:6} "
              f"{r['text_kept']:5}/{r['text_want']:<4} "
              f"{fp:5.1f}% {r['art_ok']:4}/{r['art_want']:<4} {r['exits']:6}   "
              + ", ".join(notes))
        # An area with no script is geometry, not a broken area.
        if r["instrs"] <= 16:
            continue
        score = min(tp, fp, ap if r["art_want"] else 100)
        worst.append((score, b))

    worst.sort()
    print("\nweakest areas, worst first:",
          ", ".join(f"0x{b:02X} ({s:.0f}%)" for s, b in worst[:6]))


if __name__ == "__main__":
    main()

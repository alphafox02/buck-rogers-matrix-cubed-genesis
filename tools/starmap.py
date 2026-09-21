"""
Hand the port's star map to the engine that already has one.

Countdown's Genesis build flies a solar system: bodies in their places,
moving, named. Matrix Cubed's DOS build does too, but the two engines get
there differently, and the transplant inherited the wrong half.

DOS keeps the thirteen bodies' coordinates in script variables
(0x4B85-0x4B9E), rescans them against the ship every turn, and writes the
answer into [0x4BA5]. Nothing in any script writes those coordinates -- the
DOS engine does -- so they arrived as ordinary story flags full of zeroes.
The result: a body index the story sets directly still works (Salvation
says "you are at Earth" and the port agrees), but flying can never find
anything, because the scan has nothing to match.

The Genesis engine needs none of that. It keeps the system itself and tells
the script where the ship is in [0x979B], which Countdown's own star map
reads and dispatches on. And the two games number the bodies almost
identically:

        Countdown            Matrix Cubed
  0     an encounter         nothing
  1-4   Mercury Venus Earth Mars      the same four
  5     VESTA                CERES
  6-12  FORTUNA .. THULE     VESTA .. AURORA
  13    CERES                THULE

Only Ceres sits elsewhere. So the port can use the engine's star map as it
stands: dispatch on [0x979B] and permute the fourteen jump targets into the
engine's order. That is operands only -- no instruction moves, no jump
target shifts -- and it buys the moving solar system the port never had.

The area keeps its own map. Countdown's star map loads none (LOADFILES
0x7F), and copying that looked sensible -- but Matrix Cubed's space area
really does load map 17, DOS says so, and stopping it means the area
inherits whatever was loaded before: stepping in space then printed the
DOCK's arrival text, because the dock's map and its events were still
there.

NOT YET SUFFICIENT. The dispatch and the ordering are right -- disassembling
the patched block shows index 1 reaching HIELO, 3 reaching SALVATION /
LOSANGELORG / TYCHO, 13 reaching CERES, exactly as Countdown numbers them --
but booting it leaves [0x979B] at 0, so the engine is not running its star
map for this area. Whatever switches that on is not an opcode (Countdown's
map uses none this block lacks), not the layout selector at [0x97DC], and
not the flag Countdown writes beside it. That trigger is the one thing
still missing.

Usage:
    starmap.py <in.gen> <out.gen>
"""

import struct
import sys
from pathlib import Path

import expand
import genesis_disasm as G
import genesis_ecl
import integrity

SPACE = 0x13                 # Matrix Cubed's block 19
ENGINE_BODY = 0x979B         # what Countdown's own star map dispatches on
BODIES = 14

# engine index -> the index Matrix Cubed's own dispatch uses
ORDER = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4,
         5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12, 12: 13,
         13: 5}

# What Countdown's star map asks the engine for.
VIEW_MODE = 0xBA5E     # the engine's REQUESTED screen mode
SPACE_MODE = 6         # its star map -- checked at 0x82B0 and 0xAF16

# Writing the mode straight into [0x9BBC] does not last: the engine sets
# that as it draws each screen, so an init-time write is gone by the first
# menu. [0xBA5E] is the request -- at 0x085F8 the engine copies it into
# [0x9BBC] and clears it -- so that is what a script should set.
NO_MAP = 0x7F
PIECES = 0x01


def patch(code: bytes, table=None):
    table = table or G.load_opcodes()
    found = G.disassemble(code, table)
    out, notes = bytearray(code), []
    # Countdown sets a flag in the instruction right after it writes the
    # layout selector. Match it by that position, not by its value: four
    # other SAVE 1s in this block are ordinary story flags.
    # Turn the now-dead write into the request.
    #
    # The per-turn handler opens by clearing the old body selector before
    # it rescans. Once the dispatch reads the engine's variable instead,
    # that write does nothing -- so it becomes the place to ask for the
    # star map, which is exactly the moment the area wants it: every turn,
    # after the briefing, and before the bodies are worked out.
    order = sorted(found)
    disp = next((o for o in order if found[o].name == "ONGOTO"
                 and len(found[o].args) >= 2
                 and found[o].args[1].value == BODIES), None)
    if disp is not None:
        old_sel = found[disp].args[0].value
        for o in reversed([x for x in order if x < disp]):
            ins = found[o]
            if ins.name == "SAVE" and len(ins.args) == 2 \
                    and ins.args[0].kind == "imm" and ins.args[0].value == 0 \
                    and ins.args[1].kind == "mem" and ins.args[1].value == old_sel:
                out[o + 2] = SPACE_MODE
                struct.pack_into("<H", out, o + 5, VIEW_MODE)
                notes.append(f"dead clear at 0x{o:04X} becomes "
                             f"{SPACE_MODE} -> [0x{VIEW_MODE:04X}]")
                break
    # Open the gate. The per-turn handler starts with
    #   COMPARE [gate], 0 / IFNE / GOTO away
    # and the init sets that gate to 1, so the whole space update -- the
    # rescan, and now the request for the star map -- never runs at all.
    if disp is not None:
        gate = None
        for o in order:
            ins = found[o]
            if ins.name == "COMPARE" and len(ins.args) == 2 \
                    and ins.args[0].kind == "mem" and ins.args[1].value == 0 \
                    and o < disp and o > 0x400:
                gate = ins.args[0].value
                break
        if gate is not None:
            for o in order:
                ins = found[o]
                if o < 0x100 and ins.name == "SAVE" and len(ins.args) == 2 \
                        and ins.args[0].kind == "imm" and ins.args[0].value == 1 \
                        and ins.args[1].kind == "mem" and ins.args[1].value == gate:
                    out[o + 2] = 0
                    notes.append(f"gate [0x{gate:04X}] at 0x{o:04X}: 1 -> 0")
                    break

    for off, ins in sorted(found.items()):
        if ins.name == "ONGOTO" and len(ins.args) >= 2 \
                and ins.args[1].value == BODIES and ins.args[0].kind == "mem":
            struct.pack_into("<H", out, off + 2, ENGINE_BODY)
            targets = ins.args[2:]
            if len(targets) == BODIES:
                addrs = [t.value for t in targets]
                base = targets[0].offset if hasattr(targets[0], "offset") else None
                # the tail starts after opcode + selector(3) + count(2)
                tail = off + 1 + 3 + 2
                for i in range(BODIES):
                    struct.pack_into("<H", out, tail + i * 3 + 1,
                                     addrs[ORDER[i]])
                notes.append(f"dispatch at 0x{off:04X}: selector -> "
                             f"[0x{ENGINE_BODY:04X}], targets reordered")
    return bytes(out), notes


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    rom = src.read_bytes()
    blocks = [(b, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for b, c, t in genesis_ecl.directory(rom)]
    table = G.load_opcodes()
    hits = 0
    for k, (bid, code, text) in enumerate(blocks):
        if bid != SPACE:
            continue
        new, notes = patch(code, table)
        for n in notes:
            print("  " + n)
        blocks[k] = (bid, new, text)
        hits += len(notes)
    if not hits:
        sys.exit("nothing to patch in the space block")
    b = expand.Builder(rom)
    b.relocate_ecl(blocks)
    b.relocate_geo(expand.read_geo_stream(rom))
    out = b.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

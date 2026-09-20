"""
Build a ROM that drops the party straight into one area.

Checking a transplanted area against the DOS original means standing in it,
and most areas are hours of play away. Rewriting the boot block's own
NEWECL does not get there either: the boot path this project uses restores
the pregenerated team from a save, and a save carries its own area, so the
restore puts the party back on the dock whatever the boot block said.

What does work is to let the normal boot happen and hijack the dock. Block
0x11's fifth header entry is its init hook, and overwriting the first
instructions of that hook with

    NEWECL <area>
    EXIT

means the dock loads its script, immediately switches to the target area's
block, and stops. The target's own init then runs and lays out its map.
Nothing else in the block is touched and no instruction moves, so every
jump target in it still resolves.

The EXIT matters. NEWECL swaps the code buffer under the interpreter, so
whatever follows it is read out of the NEW block at the OLD offset -- with
the dock's exit to Salvation, that landed the party in a bar with the text
of an event nobody triggered. EXIT ends the event before that can happen.

Usage:
    visit.py <in.gen> <out.gen> <area_id>
"""

import struct
import sys
from pathlib import Path

import expand
import genesis_disasm as G
import genesis_ecl
import integrity

DOCK = 0x11
HOOK = 0x10              # the fifth header entry: the area's init


def hijack(code: bytes, area: int, table=None):
    """Point the dock's init at `area` and stop there."""
    table = table or G.load_opcodes()
    found = G.disassemble(code, table)
    hook = found.get(HOOK)
    if hook is None or hook.name != "GOTO" or not hook.args:
        raise SystemExit("block 0x11 has no init hook where one was expected")
    at = hook.args[0].value - G.CODE_BASE
    ops = {name: op for op, (name, _argc) in table.items()}
    out = bytearray(code)
    out[at] = ops["NEWECL"]
    out[at + 1] = 0x00                      # a one-byte immediate
    out[at + 2] = area
    out[at + 3] = ops["EXIT"]
    return bytes(out), at


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst, area = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3], 0)
    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    if area not in [b[0] for b in blocks]:
        sys.exit(f"area 0x{area:02X} not present")
    table = G.load_opcodes()
    for k, (bid, code, text) in enumerate(blocks):
        if bid != DOCK:
            continue
        new, at = hijack(code, area, table)
        print(f"  dock init at 0x{at:04X} -> NEWECL 0x{area:02X}; EXIT")
        blocks[k] = (bid, new, text)
    b = expand.Builder(rom)
    b.relocate_ecl(blocks)
    b.relocate_geo(expand.read_geo_stream(rom))
    out = b.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

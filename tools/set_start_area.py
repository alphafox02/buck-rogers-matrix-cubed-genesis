# SPDX-License-Identifier: MIT
"""
Change which area the game boots into.

Block `0x00` is the boot script, and at offset 0x42 it does:

    00042  NEWECL     0x10
    00045  LOADFILES  0x10, 0x7F, 0xFF

`NEWECL` switches the running script to that area's block and `LOADFILES`
loads its map. Rewriting both immediates sends the player somewhere else on
start-up, which is the difference between "the ROM contains a transplanted
area" and "boot the ROM and you are standing in it".

Only the immediate operands change, so the instruction stream keeps its
length and no layout or jump target moves.

Usage:
    set_start_area.py <in.gen> <out.gen> <area_id>
"""

import sys
from pathlib import Path

import expand
import genesis_disasm as G
import genesis_ecl
import integrity


BOOT_BLOCK = 0x00


def boot_area(by_id):
    """The area the boot block loads, from its own NEWECL/LOADFILES."""
    code = by_id.get(BOOT_BLOCK)
    if code is None:
        raise SystemExit(f"no boot block 0x{BOOT_BLOCK:02X}")
    table = G.load_opcodes()
    for off, ins in sorted(G.disassemble(code, table).items()):
        if ins.name in ("NEWECL", "LOADFILES") and ins.args \
                and ins.args[0].kind == "imm" and code[off + 1] == 0x00:
            return code[off + 2]
    raise SystemExit("the boot block names no area to start in")


def retarget(code: bytes, old: int, area: int):
    """
    Point every route to `old` at `area` instead.

    Patching only the first NEWECL is not enough. The boot script offers a
    menu and reaches its NEWECL down one branch only:

        0002F  HMENU    [0x9E6F], 0x2, ...     ; two options
        0003B  COMPARE  0x1, [0x9E6F]
        00041  IFEQ
        00042  NEWECL   0x10                   ; only on choice 1

    and other blocks carry their own route to the same area. Rewriting every
    NEWECL and LOADFILES that names `old` covers whichever branch the player
    actually takes.

    Only immediate operands are touched, so instruction lengths are
    unchanged and no jump target moves.
    """
    table = G.load_opcodes()
    found = G.disassemble(code, table)
    out = bytearray(code)
    changed = []
    for off in sorted(found):
        ins = found[off]
        if ins.name not in ("NEWECL", "LOADFILES") or not ins.args:
            continue
        arg = ins.args[0]
        # type 0x00 is a one-byte immediate; anything else is a variable or
        # a wider literal and must be left alone.
        if arg.kind != "imm" or out[off + 1] != 0x00 or out[off + 2] != old:
            continue
        changed.append((off, ins.name))
        out[off + 2] = area
    return bytes(out), changed


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, dst, area = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3], 0)
    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]
    ids = [b[0] for b in blocks]
    if area not in ids:
        sys.exit(f"area 0x{area:02X} not present")

    # Whichever area the boot script currently sends the player to, read
    # out of the boot block rather than assumed.
    #
    # This used to be hardcoded to 0x10, Countdown's own opening area. The
    # port's boot block sends the player to 0x11 instead, so the constant
    # matched nothing there -- it matched a leftover NEWECL 0x10 in SSI's
    # developer block, reported success, and changed nothing the player
    # would ever reach. Every area then looked identical, because every
    # area WAS the opening dock.
    START = boot_area(dict((b[0], b[1]) for b in blocks))
    print(f"  boot block sends the player to area 0x{START:02X}")
    total = 0
    for k, (bid, code, text) in enumerate(blocks):
        new, changed = retarget(code, START, area)
        if changed:
            for off, name in changed:
                print(f"  block 0x{bid:02X} {name} at 0x{off:04X}: "
                      f"0x{START:02X} -> 0x{area:02X}")
            blocks[k] = (bid, new, text)
            total += len(changed)
    if not total:
        sys.exit(f"no NEWECL/LOADFILES targeting area 0x{START:02X} found")

    builder = expand.Builder(rom)
    builder.relocate_ecl(blocks)
    builder.relocate_geo(expand.read_geo_stream(rom))
    out = builder.finish()
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'FAILS'}; wrote {dst}")

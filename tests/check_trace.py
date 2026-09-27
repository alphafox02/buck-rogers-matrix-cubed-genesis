# SPDX-License-Identifier: MIT
"""
Validate the Genesis ECL disassembler against a live instruction trace.

The trace is the ECL program counter (a2) sampled at the opcode fetch, so
the gap between consecutive samples is the real instruction size -- ground
truth the disassembler must reproduce.

Three cases are not size mismatches and are accounted for:

  * a jump (GOTO/GOSUB/ONGOTO) whose target the trace follows,
  * a conditional (IF*) that skipped the instruction after it,
  * ENDFOR branching backwards to the top of its loop,
  * a run boundary (EXIT/RETURN), after which the VM resumes elsewhere.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import genesis_disasm as G

BASE = 0x6AF6

# The trace was captured from Countdown's own block 0x10, as its header says,
# so the block is read out of the cartridge rather than kept as a fixture --
# it is SSI's bytecode and does not belong in this repository.
#
# It used to be read from extracted/genesis_ecl/10.ecl.bin, which is generated
# and not committed. That file had since been overwritten by a Matrix Cubed
# build, leaving a 195-byte boot block where a 2087-byte one was wanted, and
# the test had been failing against it unnoticed.
REPO = Path(__file__).resolve().parent.parent
ROM = REPO / "roms/countdown.gen"
TRACE_BLOCK = 0x10


def samples(path):
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.append([int(tok, 16) for tok in line.split()])
    return out


def block():
    """Countdown's block 0x10, decompressed out of the cartridge."""
    import genesis_ecl
    rom = ROM.read_bytes()
    for bid, code, _text in genesis_ecl.directory(rom):
        if bid == TRACE_BLOCK:
            return bytes(genesis_ecl.decompress(code))
    raise SystemExit(f"block 0x{TRACE_BLOCK:02X} is not in {ROM}")


def main():
    if not ROM.exists():
        print(f"skipped: {ROM.relative_to(REPO)} is not present. This test reads\n"
              f"the traced block out of the cartridge; supply one and run again.")
        return 0
    table = G.load_opcodes()
    code = block()
    ok = flow = bad = 0

    for run in samples(Path(__file__).with_name("trace_block10.txt")):
        offs = [a - BASE for a in run]
        for i in range(len(offs) - 1):
            here, nxt = offs[i], offs[i + 1]
            gap = nxt - here
            ins = G.decode(code, here, table)
            if ins is None:
                print(f"  0x{here:04X}  FAILED TO DECODE")
                bad += 1
                continue
            if ins.size == gap:
                ok += 1
                continue
            # Control flow rather than a size error?
            targets = [a.value - BASE for a in ins.args if a.kind == "mem"]
            if ins.name in G.JUMPS and nxt in targets:
                flow += 1
            elif ins.name.startswith("IF") and gap > ins.size:
                flow += 1
            elif ins.name == "ENDFOR" and gap < 0:
                flow += 1          # loops back to its FOR
            elif ins.name in ("EXIT", "RETURN"):
                flow += 1
            else:
                print(f"  0x{here:04X}  expected {gap}, decoded {ins.size}"
                      f"  {ins.render()}")
                bad += 1

    print(f"{ok} exact, {flow} explained by control flow, {bad} mismatched")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

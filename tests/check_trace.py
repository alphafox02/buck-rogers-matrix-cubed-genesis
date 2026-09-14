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
BLOCK = "extracted/genesis_ecl/10.ecl.bin"


def samples(path):
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.append([int(tok, 16) for tok in line.split()])
    return out


def main():
    table = G.load_opcodes()
    code = Path(BLOCK).read_bytes()
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

# SPDX-License-Identifier: MIT
"""
Disassemble every ECL block in a .DAX file to readable text.

Usage:
    python3 dump_ecl.py <out_dir> <ECL1.DAX> [...]

Writes one .ecl listing per block plus a summary.txt with opcode
statistics and per-block coverage.
"""

import collections
import sys
from pathlib import Path

import dax
import ecl


def dump(sources, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    freq = collections.Counter()
    rows = []
    total_bytes = covered = 0

    for src in sources:
        stem = Path(src).stem
        for block_id, block in sorted(dax.load(src).items()):
            instructions, stop, err = ecl.disassemble(block)
            total_bytes += len(block)
            covered += stop
            for ins in instructions:
                freq[ins.name] += 1

            lines = [
                f"; {stem} block {block_id}",
                f"; {len(block)} bytes, {len(instructions)} instructions, "
                f"{stop / len(block) * 100:.1f}% decoded",
            ]
            if err:
                lines.append(f"; stopped: {err}")
            lines.append("")
            lines += [f"{i.offset:05X}  {i}" for i in instructions]

            dest = out / stem
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{block_id:03d}.ecl").write_text("\n".join(lines) + "\n")
            rows.append((stem, block_id, len(block), len(instructions),
                         stop / len(block) * 100, err or ""))

    total = sum(freq.values())
    summary = [
        f"{total} instructions across {len(rows)} blocks",
        f"{len(freq)} distinct opcodes",
        f"{covered / total_bytes * 100:.1f}% of {total_bytes} bytes decoded",
        "",
        "Per block:",
    ]
    for stem, bid, size, n, cov, err in rows:
        summary.append(f"  {stem} {bid:3d}  {size:6d} B  {n:5d} instr  "
                       f"{cov:5.1f}%  {err}")
    summary += ["", "Opcode frequency:"]
    for name, count in freq.most_common():
        summary.append(f"  {name:24s} {count:6d}  {count / total * 100:5.2f}%")

    (out / "summary.txt").write_text("\n".join(summary) + "\n")
    print(f"wrote {len(rows)} listings to {out}/")
    print(f"{total} instructions, {len(freq)} distinct opcodes, "
          f"{covered / total_bytes * 100:.1f}% decoded")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: dump_ecl.py <out_dir> <file.DAX> [...]")
    dump(sys.argv[2:], sys.argv[1])

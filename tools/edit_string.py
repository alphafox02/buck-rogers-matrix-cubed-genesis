# SPDX-License-Identifier: MIT
"""
Edit a string inside a Genesis ECL text resource and rebuild the ROM.

Proves the development loop end to end: decompress, modify, recompress,
write, verify.

Replacement text is padded or truncated to the original length. Strings are
addressed by byte offset from ECL instructions, so changing a length would
shift every later string in that block and silently corrupt the references.
Keeping the length fixed avoids rewriting the argument of every affected
instruction.

Usage:
    edit_string.py <in.gen> <out.gen> <block_id> <index> <new text>
"""

import sys
from pathlib import Path

import genesis_ecl
import rebuild_ecl


def replace_nth(text: bytes, index: int, new: str) -> bytes:
    parts = text.split(b"\0")
    targets = [i for i, p in enumerate(parts) if p.strip()]
    if index >= len(targets):
        raise SystemExit(f"block has only {len(targets)} non-empty strings")
    slot = targets[index]
    original = parts[slot]
    replacement = new.encode("ascii", "replace")[:len(original)]
    replacement = replacement.ljust(len(original))
    print(f"  was: {original.decode('latin1')!r}")
    print(f"  now: {replacement.decode('latin1')!r}")
    parts[slot] = replacement
    return b"\0".join(parts)


if __name__ == "__main__":
    if len(sys.argv) < 6:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    block_id, index, new = int(sys.argv[3], 0), int(sys.argv[4]), " ".join(sys.argv[5:])

    rom = src.read_bytes()
    blocks = [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rom)]

    out = []
    for bid, code, text in blocks:
        if bid == block_id:
            print(f"block 0x{bid:02X}, string {index}:")
            text = replace_nth(text, index, new)
        out.append((bid, code, text))

    rebuilt = rebuild_ecl.rebuild(rom, out)
    dst.write_bytes(rebuilt)
    print(f"wrote {dst}")

    check = {b[0]: b[2] for b in
             [(bid, genesis_ecl.decompress(c), genesis_ecl.decompress(t))
              for bid, c, t in genesis_ecl.directory(rebuilt)]}
    expected = {b[0]: b[2] for b in out}
    print("verified: text resources match intent"
          if check == expected else "VERIFY FAILED")

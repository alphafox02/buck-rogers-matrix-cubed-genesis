"""
Run Matrix Cubed's own demo instead of nothing.

DOS shows a demo from its title screen -- the bar reads "MATRIX CUBED V1.0
PLAY  DEMO" -- narration over portraits, the party walking a corridor in first
person, then a combat. Captured from DOSBox at period speed it starts about 48
seconds in and runs for the best part of a minute.

It is **already in the ROM**. `build.py` transplants every ECL1 block, and the
demo is block 24, so it is area `0x18`: 103 instructions, LOADFILES 0x40,
LOADPIECES 7, three ADDNPCs, the portraits and narration, the walk loop, the
fight. Nothing has ever invoked it.

Two bytes decide that:

* `0x0414C` -- the entry dispatch reads `[0xBA5A]` and, when set, sends the
  player into area **0x03**, which is Countdown's narration about NEO and RAM.
  Pointing it at 0x18 runs Matrix Cubed's demo instead.
* `0x0038A` -- boot waits about 0x384 polls for input and sets `[0xBA5A]` on a
  timeout. `tools/trim_intro.py` replaced that `st.b` with `clr.b` precisely
  because the demo it reached was the wrong game's. With 0x18 in place there is
  something right to reach, so it goes back.

Both are inside the checksummed first megabyte, so the sum is repaired after.

Usage:
    demomode.py <in.gen> <out.gen> [--off]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integrity

DISPATCH = 0x0414C          # move.b #$3, $b9f0.w
DISPATCH_WAS = bytes.fromhex("11fc0003b9f0")
DISPATCH_NOW = bytes.fromhex("11fc0018b9f0")   # area 0x18
TIMEOUT = 0x0038A           # clr.b $ba5a.w  /  st.b $ba5a.w
TIMEOUT_OFF = bytes.fromhex("4238ba5a")
TIMEOUT_ON = bytes.fromhex("50f8ba5a")


def patch(rom: bytes, on=True):
    out = bytearray(rom)
    d = bytes(out[DISPATCH:DISPATCH + 6])
    if d not in (DISPATCH_WAS, DISPATCH_NOW):
        raise SystemExit(f"0x{DISPATCH:05X} is not the dispatch: {d.hex()}")
    out[DISPATCH:DISPATCH + 6] = DISPATCH_NOW if on else DISPATCH_WAS
    t = bytes(out[TIMEOUT:TIMEOUT + 4])
    if t not in (TIMEOUT_OFF, TIMEOUT_ON):
        raise SystemExit(f"0x{TIMEOUT:05X} is not the timeout: {t.hex()}")
    out[TIMEOUT:TIMEOUT + 4] = TIMEOUT_ON if on else TIMEOUT_OFF
    print(f"  dispatch at 0x{DISPATCH:05X} -> area 0x{'18' if on else '03'}")
    print(f"  timeout at 0x{TIMEOUT:05X} -> {'sets' if on else 'clears'} [0xBA5A]")
    return bytes(out)


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    out = integrity.repair(patch(src.read_bytes(), "--off" not in sys.argv))
    dst.write_bytes(out)
    print(f"checksum {'verifies' if integrity.verify(out) else 'BAD'}; wrote {dst}")

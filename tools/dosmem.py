"""
Read the DOS game's ECL variables out of a running DOSBox.

Some of what the scenario needs is never written by any script -- the
positions of the thirteen bodies on the star map sit at 0x4B85-0x4B9E and
are only ever read -- so the values exist only inside the running engine.
Reading them is the difference between knowing the port is missing its
solar system and being able to put it back.

Finding the DOS data segment inside DOSBox's address space needs one
anchor, and the ECL bytecode is a good one: jump targets in a block are
offsets from 0x8000, so wherever the loaded block's bytes appear in memory
is the segment's 0x8000. Everything else follows by subtraction.

Linux will not let a process read an unrelated one when
/proc/sys/kernel/yama/ptrace_scope is 1, which it is here, so DOSBox is
started as a child of this module rather than attached to afterwards.

Usage:
    dosmem.py <addr> [count]      e.g. dosmem.py 0x4B85 26
"""

import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dax

REPO = Path(__file__).resolve().parent.parent
CODE_BASE = 0x8000
ECL = REPO / "dos_game/matrix/ECL1.DAX"


def launch(wait=14):
    p = subprocess.Popen(["dosbox", "-conf", "tools/matrix.conf"], cwd=REPO,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(wait)
    return p


def _regions(pid):
    for line in open(f"/proc/{pid}/maps"):
        m = re.match(r"([0-9a-f]+)-([0-9a-f]+) (\S+)", line)
        if not m or "r" not in m.group(3):
            continue
        lo, hi = int(m.group(1), 16), int(m.group(2), 16)
        if hi - lo >= 0x10000:
            yield lo, hi


def find_segment(pid, blocks=None):
    """[(segment base, block id)] for every loaded ECL block found."""
    blocks = blocks or dax.load(ECL)
    mem = open(f"/proc/{pid}/mem", "rb", 0)
    out = []
    for lo, hi in _regions(pid):
        try:
            mem.seek(lo)
            buf = mem.read(hi - lo)
        except (OSError, ValueError, OverflowError):
            continue
        for bid, code in blocks.items():
            needle = code[:64]
            start = 0
            while True:
                i = buf.find(needle, start)
                if i < 0:
                    break
                out.append((lo + i - CODE_BASE, bid))
                start = i + 1
    return out, mem


def read(mem, base, addr, count=1):
    mem.seek(base + addr)
    return mem.read(count)


if __name__ == "__main__":
    addr = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x4B85
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 26
    proc = launch()
    try:
        found, mem = find_segment(proc.pid)
        print(f"dosbox pid {proc.pid}: {len(found)} segment candidates")
        for base, bid in found:
            raw = read(mem, base, addr, count)
            print(f"  base 0x{base:x} (block {bid}) -> {raw.hex()}")
    finally:
        proc.terminate()

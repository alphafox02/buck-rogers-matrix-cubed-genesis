"""
Disassemble extracted Genesis ECL bytecode.

Argument encoding is identical to the DOS engine (see docs/re_notes.md), but
the opcode numbering diverges past 0x1C and the Genesis adds 17 opcodes of
its own. Argument counts come from docs/opcode_args.md, derived two
independent ways and cross-checked.

Strings are out of line on the Genesis: a string argument is an offset into
the block's companion text resource, not inline packed text as in DOS. Pass
the matching `.text.bin` to resolve them.
"""

import re
import struct
from pathlib import Path

# Payload sizes by argument type. Type 0x80 is 2 bytes on the Genesis -- a
# string OFFSET, not the DOS engine's inline packed string. Confirmed by a
# live trace: `12 80 00 00` (PRINTCLEAR) measured 4 bytes, and the argument
# fetcher at 0x0404A adds type-0x80 values to the ECL base at $FFB9A4.
ARG_SIZE = {0x00: 1, 0x01: 2, 0x02: 2, 0x03: 2, 0x04: 4, 0x05: 2,
            0x80: 2, 0x81: 2}
CODE_BASE = 0x6AF6

# Opcodes taking a fixed head plus a variable tail, with the index of the
# fixed argument that gives the tail length. Mirrors the DOS engine.
DYNAMIC = {0x15: 2, 0x25: 1, 0x26: 1, 0x27: 1, 0x2B: 1, 0x31: 1, 0x5D: 0}

# Fixed-argument counts for the dynamic opcodes, taken from the DOS engine.
# Neither derivation method can measure these correctly: the static pass
# counts fetcher calls inside the tail loop, and the inference pass has no
# model of a variable tail. Getting ONGOTO wrong (3 instead of 2) consumes
# the first jump target as a fixed argument, then reads one entry too many
# and fails on the last -- which is what truncated most large blocks.
DYNAMIC_FIXED = {0x15: 3, 0x25: 2, 0x26: 2, 0x27: 2, 0x2B: 2, 0x31: 2, 0x5D: 1}

TERMINAL = {"EXIT", "RETURN", "GOTO", "ONGOTO"}
JUMPS = {"GOTO", "GOSUB", "ONGOTO", "ONGOSUB"}

# IF* opcodes execute the following instruction only when the test passes,
# and skip over it when it fails. BOTH continuations are reachable, so a
# walk must queue the address past the guarded instruction as well --
# otherwise any IF-guarded EXIT looks like the end of the run and truncates
# everything after it. Confirmed by live trace: the same IFNE shows a gap of
# 1 byte when it falls through and 2 when it skips a one-byte EXIT.
CONDITIONAL = ("IFEQ", "IFNE", "IFLT", "IFGT", "IFLE", "IFGE")


DOC = Path(__file__).resolve().parent.parent / "docs" / "opcode_args.md"


# Where the generated table is marked LOW confidence and the two methods
# disagree, the handler itself is the tie-breaker and wins.
#
#   0x3D CLEARBOX -- static 0, inferred 1, "LOW -- methods disagree". The
#   handler is `bsr.w $8710 / rts`, and 0x8710 is a screen-drawing routine
#   (VDP register writes at (a4)), not an argument fetcher. Taking the
#   inferred 1 made the interpreter read the following instruction as an
#   argument: emitted after the shop's redraw it desynced the script, and
#   the party came out of the store on the wrong square.
HANDLER_SAYS = {0x3D: 0}


def load_opcodes(doc=None):
    """Parse the generated opcode table into {op: (name, argc)}."""
    doc = DOC if doc is None else doc
    rows = re.findall(
        r"\| `0x([0-9A-F]{2})` \| `(\w+)` \| (\d+) \| (\d+|\?) \| \d+/\d+ \| ([^|]+)\|",
        Path(doc).read_text(),
    )
    table = {}
    for op_hex, name, static, inferred, conf in rows:
        op = int(op_hex, 16)
        if op in HANDLER_SAYS:
            table[op] = (name, HANDLER_SAYS[op])
            continue
        # Trust the static count where inference cannot apply, or where the
        # two disagree and inference had no clear majority.
        if op in DYNAMIC_FIXED:
            argc = DYNAMIC_FIXED[op]
        elif "dynamic" in conf or inferred == "?":
            argc = int(static)
        else:
            argc = int(inferred)
        table[op] = (name, argc)
    return table


class Arg:
    __slots__ = ("kind", "value", "size")

    def __init__(self, kind, value, size):
        self.kind, self.value, self.size = kind, value, size

    def render(self, text=None):
        if self.kind == "str":
            if text is not None and self.value < len(text):
                end = text.find(b"\0", self.value)
                body = text[self.value:end if end >= 0 else len(text)]
                return '"%s"' % body.decode("latin1")
            return f"str[0x{self.value:04X}]"
        if self.kind == "mem":
            return f"[0x{self.value:04X}]"
        return f"0x{self.value:X}"


def read_arg(code, pos):
    if pos >= len(code):
        return None
    t = code[pos]
    if t not in ARG_SIZE:
        return None
    size = ARG_SIZE[t]
    raw = code[pos + 1:pos + 1 + size]
    if len(raw) < size:
        return None
    value = (raw[0] if size == 1 else
             struct.unpack("<H", raw)[0] if size == 2 else
             struct.unpack("<I", raw)[0])
    kind = "str" if t in (0x80, 0x81) else ("mem" if t & 1 else "imm")
    return Arg(kind, value, 1 + size)


class Instruction:
    __slots__ = ("offset", "size", "op", "name", "args")

    def __init__(self, offset, size, op, name, args):
        self.offset, self.size, self.op, self.name, self.args = offset, size, op, name, args

    def render(self, text=None):
        return f"{self.name:16} " + ", ".join(a.render(text) for a in self.args)


def decode(code, pos, table):
    if pos >= len(code):
        return None
    op = code[pos]
    if op not in table:
        return None
    name, argc = table[op]
    args = []
    p = pos + 1
    for _ in range(argc):
        a = read_arg(code, p)
        if a is None:
            return None
        args.append(a)
        p += a.size
    dyn = DYNAMIC.get(op)
    if dyn is not None and dyn < len(args):
        n = args[dyn].value
        if not isinstance(n, int) or n > 64:
            return None
        for _ in range(n):
            a = read_arg(code, p)
            if a is None:
                return None
            args.append(a)
            p += a.size
    return Instruction(pos, p - pos, op, name, args)


def disassemble(code, table):
    """Walk from the five event hooks, following every jump target."""
    found, queue = {}, []
    pos = 0
    for _ in range(5):                       # the event-hook header
        ins = decode(code, pos, table)
        if ins is None:
            break
        found[pos] = ins
        pos += ins.size
        queue += [a.value - CODE_BASE for a in ins.args if a.kind == "mem"]
    queue.append(pos)

    while queue:
        p = queue.pop()
        while 0 <= p < len(code) and p not in found:
            ins = decode(code, p, table)
            if ins is None:
                break
            found[p] = ins
            if ins.name in JUMPS:
                queue += [a.value - CODE_BASE for a in ins.args
                          if a.kind == "mem" and 0 <= a.value - CODE_BASE < len(code)]
            if ins.name.startswith("IF") and ins.name in CONDITIONAL:
                guarded = decode(code, p + ins.size, table)
                if guarded is not None:
                    skip = p + ins.size + guarded.size
                    if skip < len(code):
                        queue.append(skip)
            if ins.name in TERMINAL:
                break
            p += ins.size
    return found


if __name__ == "__main__":
    import sys
    table = load_opcodes()
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "extracted/genesis_ecl")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "extracted/genesis_ecl_disasm")
    out.mkdir(parents=True, exist_ok=True)
    total = covered = count = 0
    for f in sorted(src.glob("*.ecl.bin")):
        code = f.read_bytes()
        tf = f.with_name(f.name.replace(".ecl.bin", ".text.bin"))
        text = tf.read_bytes() if tf.exists() else None
        found = disassemble(code, table)
        claimed = sum(i.size for i in found.values())
        total += len(code); covered += claimed; count += len(found)
        lines = [f"; {f.name}  {len(code)} bytes, {len(found)} instructions, "
                 f"{claimed / len(code) * 100:.1f}% reached"]
        lines += [f"{o:05X}  {found[o].render(text)}" for o in sorted(found)]
        (out / f.name.replace(".ecl.bin", ".ecl")).write_text("\n".join(lines) + "\n")
        print(f"  {f.name:14} {len(code):6d}B  {claimed/len(code)*100:5.1f}%  {len(found):5d} instr")
    print(f"\n{count} instructions, {covered/total*100:.1f}% of {total} bytes reached")

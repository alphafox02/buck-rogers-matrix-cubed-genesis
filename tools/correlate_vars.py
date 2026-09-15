"""
Match DOS engine variables to their Genesis counterparts by behaviour.

Addresses cannot be matched by value -- the two engines lay memory out
differently -- so each variable is described by a signature built from how
scripts use it, and signatures are matched across engines.

A signature captures things the engine's own semantics force:

    opcodes   which instructions touch it, and in which operand position
    values    the distribution of immediates it is compared or assigned
    range     the largest value seen, which bounds what it can represent

A direction variable is compared against 0-3 and nothing else, in every
game that has directions. A map coordinate tops out at 15 on a 16x16 grid.
A scratch register is overwhelmingly the destination of bitwise operations.
Those constraints come from the design, not from either implementation, so
they survive the port.

Frequency rank alone is not enough: it agrees on the busiest one or two
addresses and diverges immediately after.
"""

import collections
import math
from pathlib import Path

import dax
import ecl
import genesis_disasm as G
import genesis_ecl

REPO = Path(__file__).resolve().parent.parent
GEN_JUMPS = {"GOTO", "GOSUB", "ONGOTO", "ONGOSUB"}
DOS_JUMPS = {"GOTO", "GOSUB", "ON_GOTO", "ON_GOSUB"}

# DOS mnemonic -> Genesis mnemonic, for comparing opcode signatures.
EQUIV = {
    "WRITE_MEM": "SAVE", "COMPARE": "COMPARE", "ADD": "ADD",
    "SUBTRACT": "SUBTRACT", "AND": "AND", "OR": "OR",
    "COMPARE_AND": "COMPAREAND", "RANDOM": "RANDOM",
    "MULTIPLY": "MULTIPLY", "DIVIDE": "DIVIDE",
    "INPUT_NUMBER": "INPUTNUMBER", "FOR_START": "FOR",
}


class Signature:
    __slots__ = ("opcodes", "values", "count", "top")

    def __init__(self):
        self.opcodes = collections.Counter()
        self.values = collections.Counter()
        self.count = 0
        self.top = -1

    def add(self, opcode, position, immediates):
        self.opcodes[(opcode, position)] += 1
        self.count += 1
        for v in immediates:
            self.values[v] += 1
            self.top = max(self.top, v)


def _normalise(counter):
    total = sum(counter.values()) or 1
    return {k: v / total for k, v in counter.items()}


def _cosine(a, b):
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values())) or 1
    nb = math.sqrt(sum(v * v for v in b.values())) or 1
    return dot / (na * nb)


def genesis_signatures(rom):
    table = G.load_opcodes()
    sigs = collections.defaultdict(Signature)
    for _bid, code, _text in genesis_ecl.directory(rom):
        for ins in G.disassemble(genesis_ecl.decompress(code), table).values():
            if ins.name in GEN_JUMPS:
                continue
            imm = [a.value for a in ins.args if a.kind == "imm"]
            for pos, a in enumerate(ins.args):
                if a.kind == "mem":
                    sigs[a.value].add(ins.name, pos, imm)
    return sigs


def dos_signatures(path):
    sigs = collections.defaultdict(Signature)
    for _bid, block in dax.load(path).items():
        found, _entries, _errors = ecl.disassemble_block(block)
        for ins in found.values():
            if ins.name in DOS_JUMPS:
                continue
            imm = [a.value for a in ins.args
                   if not a.is_memory and a.type != 0x80 and isinstance(a.value, int)]
            name = EQUIV.get(ins.name, ins.name)
            for pos, a in enumerate(ins.args):
                if a.is_memory:
                    sigs[a.value].add(name, pos, imm)
    return sigs


def score(dos: Signature, gen: Signature) -> float:
    op = _cosine(_normalise(dos.opcodes), _normalise(gen.opcodes))
    val = _cosine(_normalise(dos.values), _normalise(gen.values))
    # A variable that tops out at 15 cannot be one that reaches 200.
    if dos.top >= 0 and gen.top >= 0:
        lo, hi = sorted((dos.top + 1, gen.top + 1))
        rng = lo / hi
    else:
        rng = 0.5
    return 0.45 * op + 0.35 * val + 0.20 * rng


def rank(dos_sigs, gen_sigs, address, limit=3):
    d = dos_sigs[address]
    scored = [(score(d, g), a) for a, g in gen_sigs.items() if g.count >= 8]
    scored.sort(reverse=True)
    return scored[:limit]

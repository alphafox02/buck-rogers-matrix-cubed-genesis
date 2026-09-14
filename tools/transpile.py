"""
Translate DOS Gold Box ECL into Genesis ECL.

The two engines share an argument encoding and roughly two thirds of their
opcode numbering, so this is a table remap plus one real transformation:
strings move out of line.

    DOS      inline, 6-bit packed, introduced by a length byte
    Genesis  a 2-byte offset into a separate text resource

Because that changes instruction sizes, every jump target shifts, so this
assembles in two passes: lay out instructions to learn the new offsets, then
emit with corrected targets. Jump arguments are also rebased from the DOS
code base (0x8000) to the Genesis one (0x6AF6).

What this does NOT do is invent semantics. Opcodes with no Genesis
counterpart are reported, not guessed at -- see docs/compatibility.md.
"""

import struct
from collections import OrderedDict

import ecl
import genesis_disasm as G

DOS_BASE = 0x8000
GEN_BASE = G.CODE_BASE          # 0x6AF6

# DOS mnemonic -> Genesis mnemonic. Same-slot opcodes with differing names
# are only mapped where the roles genuinely correspond.
NAME_MAP = {
    "WRITE_MEM": "SAVE", "LOAD_CHAR": "LOADCHARACTER", "LOAD_MON": "LOADMONSTER",
    "SPRITE_START": "SETUPMONSTERS", "SPRITE_ADVANCE": "APPROACH",
    "INPUT_NUMBER": "INPUTNUMBER", "INPUT_STRING": "INPUTSTRING",
    "PRINT_CLEAR": "PRINTCLEAR", "COMPARE_AND": "COMPAREAND",
    "MENU_VERTICAL": "MENU", "IF_EQUALS": "IFEQ", "IF_NOT_EQUALS": "IFNE",
    "IF_LESS": "IFLT", "IF_GREATER": "IFGT", "IF_LESS_EQUALS": "IFLE",
    "IF_GREATER_EQUALS": "IFGE", "CLEAR_MON": "CLEARMONSTERS",
    "PARTY_CHECK": "CHECKPARTY", "SPACE_COMBAT": "SPACECOMBAT",
    "NEW_ECL": "NEWECL", "LOAD_AREA_MAP": "LOADFILES", "SKILL_CHECK": "SKILL",
    "PARTY_SKILL_CHECK": "PRINTSKILL", "ON_GOTO": "ONGOTO", "ON_GOSUB": "ONGOSUB",
    "MENU_HORIZONTAL": "HMENU", "INPUT_YES_NO": "GETYN", "FIND_ITEM": "FINDITEM",
    "PRINT_RETURN": "PRINTRETURN", "NPC_ADD": "ADDNPC",
    "LOAD_AREA_DECO": "LOADPIECES", "LOGBOOK_ENTRY": "JOURNAL",
    "DESTROY_ITEM": "DESTROY", "GIVE_EXP": "ADDEP", "SPELL": "SPELLS",
    "CLEAR_BOX": "CLEARBOX", "COPY_PROTECTION": "PROTECT", "FOR_START": "FOR",
    "FOR_REPEAT": "ENDFOR", "STOP_MOVE": "CONTINUE", "SOUND_EVENT": "SOUND",
    "CLOCK1": "CLOCK",
    # Same slot, same role: both halt until the player acknowledges.
    "INPUT_RETURN": "CONTINUE",
}


def genesis_opcodes():
    """Genesis mnemonic -> (opcode number, fixed argument count)."""
    table = G.load_opcodes()
    return {name: (op, argc) for op, (name, argc) in table.items()}


class Unsupported(Exception):
    pass


class StringPool:
    """Collects text and hands back byte offsets, sharing duplicates."""

    def __init__(self):
        self._offsets = OrderedDict()
        self._size = 0

    def intern(self, text: str) -> int:
        if text not in self._offsets:
            self._offsets[text] = self._size
            self._size += len(text) + 1
        return self._offsets[text]

    def build(self) -> bytes:
        out = bytearray()
        for text in self._offsets:
            out += text.encode("ascii", "replace") + b"\0"
        return bytes(out)


def _encode_arg(kind, value):
    """Emit a Genesis argument. Types match the DOS engine exactly."""
    if kind == "str":
        return bytes([0x80]) + struct.pack("<H", value)
    if kind == "mem":
        return bytes([0x01]) + struct.pack("<H", value)
    if value <= 0xFF:
        return bytes([0x00, value])
    if value <= 0xFFFF:
        return bytes([0x02]) + struct.pack("<H", value)
    return bytes([0x04]) + struct.pack("<I", value)


def transpile(block: bytes):
    """
    Translate one DOS ECL block.

    Returns (genesis_code, text_pool, report) where report lists any
    instructions that could not be translated.
    """
    found, _entries, _errors = ecl.disassemble_block(block)
    gen = genesis_opcodes()
    pool = StringPool()
    report = []

    order = sorted(found)
    # Pass 1: lay out, learning each instruction's new offset.
    layout, pos = {}, 0
    pieces = []
    for off in order:
        ins = found[off]
        name = NAME_MAP.get(ins.name, ins.name)
        if name not in gen:
            report.append((off, ins.name, "no Genesis counterpart"))
            continue
        opcode, _ = gen[name]
        args = []
        for arg in list(ins.args) + list(ins.dyn_args):
            if arg.type == 0x80:
                args.append(("str", pool.intern(str(arg.value))))
            elif arg.is_memory:
                args.append(("mem", arg.value))    # rebased in pass 2
            else:
                args.append(("imm", arg.value))
        size = 1 + sum(len(_encode_arg(k, v if k != "mem" else 0)) for k, v in args)
        layout[off] = pos
        pieces.append((off, opcode, args))
        pos += size

    # Pass 2: emit, rebasing jump targets through the new layout.
    out = bytearray()
    for off, opcode, args in pieces:
        out.append(opcode)
        for kind, value in args:
            if kind == "mem":
                target = value - DOS_BASE
                if target in layout:
                    value = layout[target] + GEN_BASE
                else:
                    value = value - DOS_BASE + GEN_BASE
            out += _encode_arg(kind, value)
    return bytes(out), pool.build(), report

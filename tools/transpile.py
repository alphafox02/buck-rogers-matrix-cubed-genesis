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

Two classes of memory argument must be told apart. Arguments of a jump
instruction are code addresses and get rebased through the new layout;
everything else is a variable address and must not be touched by the
rebase.

What this does NOT do is invent semantics:

  * Opcodes with no Genesis counterpart are reported, not guessed at --
    see docs/compatibility.md.
  * Engine-shared variables are translated only where the mapping has been
    established (see docs/variable_map.md); the rest pass through and are
    reported. Script-only story flags are reallocated by `flagmap`, which
    matters more than it sounds: DOS keeps them below 0x8000, and Genesis
    ECL addresses sign-extend, so untranslated they would resolve into ROM
    and the writes would vanish.
"""

import struct
from collections import OrderedDict

import ecl
import flagmap
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


STUB_OPCODE = 0xFF          # outside the valid 0x00-0x5D range


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
    if kind in ("code", "var"):
        return bytes([0x01]) + struct.pack("<H", value & 0xFFFF)
    if value <= 0xFF:
        return bytes([0x00, value])
    if value <= 0xFFFF:
        return bytes([0x02]) + struct.pack("<H", value)
    return bytes([0x04]) + struct.pack("<I", value)


# Engine-shared variables whose Genesis counterpart is established.
VARIABLE_MAP = {
    0x4BF2: 0x97E8,    # LAST_ECL, the current area
    0xC04B: 0x9AF6,    # DUNGEON_X
    0xC04C: 0x9AF7,    # DUNGEON_Y
    0xC04D: 0x9AFA,    # DUNGEON_DIR
    0xC04E: 0x97AD,    # MAP_WALL_TYPE     -- both top out at exactly 12
    0xC04F: 0x9AF9,    # MAP_SQUARE_INFO   -- both dominated by 63 (0x3F mask)
    0x7EC7: 0x9DBD,    # COMBAT_RESULT     -- tested against 128 in both
    0x7EC9: 0x9DBF,    # MOVEMENT_BLOCK    -- 255 in 63/63 and 57/57 uses
    0x7EB1: 0x9DA7,    # INDEX_OF_SEL_PC   -- the resolver indexes by it
}

# Mappings supported by good evidence but not by a constraint that admits
# only one answer. Applied, because the alternative is worse rather than
# safer: an unmapped DOS address below 0x8000 sign-extends into ROM, so the
# write is silently discarded and a party loop never advances. A probable
# mapping at least fails visibly and in one place.
#
# Kept separate so a later contradiction is cheap to act on.
PROBABLE_MAP = {
    # The only non-scratch operand of LOAD_CHAR / LOADCHARACTER on each side,
    # 27 uses against 10. Scripts use it to walk the party.
    0x4CF6: 0x98EC,    # FOR_LOOP_COUNT
}

# Contiguous banks that map as ranges: (dos_lo, dos_hi, genesis_lo).
#
# The scratch bank is consecutive in both engines -- 0x7F79/0x7F7A/0x7F7B
# against 0x9E6F/0x9E70/0x9E71 -- so the slots beyond the three confirmed by
# usage follow by construction rather than by guesswork. Scripts use the
# bank as an array, indexing several slots deep for nested expressions.
#
# The two per-character windows are ranges by definition: the address
# resolver at 0x042E0 redirects each as a block.
WINDOW_MAP = (
    (0x7F79, 0x7F80, 0x9E6F),      # scratch bank
    (0x7C00, 0x7C4D, 0x9AFC),      # selected-character record
    (0x7D00, 0x7D1A, 0x9BF6),      # selected-character status
)


def map_variable(addr, flags, report, offset):
    """Translate one DOS variable address, or report it untranslated."""
    if addr in VARIABLE_MAP:
        return VARIABLE_MAP[addr]
    if addr in PROBABLE_MAP:
        return PROBABLE_MAP[addr]
    for lo, hi, base in WINDOW_MAP:
        if lo <= addr < hi:
            return base + (addr - lo)
    if addr in flags:
        return flags[addr]
    report.append((offset, f"var 0x{addr:04X}", "no Genesis mapping"))
    return addr


def transpile(block: bytes, flags=None):
    """
    Translate one DOS ECL block.

    Returns (genesis_code, text_pool, report) where report lists any
    instructions that could not be translated.
    """
    if flags is None:
        flags = {}
    found, _entries, _errors = ecl.disassemble_block(block)
    # DOS code is addressed from 0x8000, and 0x8000 is the first byte AFTER
    # the 5000 marker -- so converting a jump target to a block offset must
    # add the marker size back, exactly as ecl._targets does.
    marker = ecl.code_start(block)
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
        if name in gen:
            opcode, _ = gen[name]
        else:
            # Emit a stub rather than dropping the instruction. Dropping it
            # would remove its offset from the layout and strand every jump
            # that targets it, turning one untranslatable opcode into dozens
            # of broken branches. 0xFF is outside the 94-opcode range, so a
            # stub is unmistakable and cannot be mistaken for working code.
            report.append((off, ins.name, "no Genesis counterpart"))
            opcode = STUB_OPCODE
        is_jump = ins.name in ecl._JUMPS
        args = []
        for arg in list(ins.args) + list(ins.dyn_args):
            if arg.type == 0x80:
                args.append(("str", pool.intern(str(arg.value))))
            elif arg.is_memory:
                # Only a jump's operands are code addresses.
                if is_jump:
                    args.append(("code", arg.value))
                else:
                    args.append(("var", map_variable(arg.value, flags, report, off)))
            else:
                args.append(("imm", arg.value))
        size = 1 + sum(len(_encode_arg(k, 0 if k in ("code", "var") else v))
                       for k, v in args)
        layout[off] = pos
        pieces.append((off, opcode, args))
        pos += size

    # Pass 2: emit, rebasing jump targets through the new layout.
    out = bytearray()
    for off, opcode, args in pieces:
        out.append(opcode)
        for kind, value in args:
            if kind == "code":
                target = value - DOS_BASE + marker
                if target in layout:
                    value = layout[target] + GEN_BASE
                else:
                    report.append((off, "jump", f"target 0x{value:04X} not in layout"))
                    value = GEN_BASE
            out += _encode_arg(kind, value)
    return bytes(out), pool.build(), report

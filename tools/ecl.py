"""
ECL bytecode disassembler for SSI Gold Box games.

ECL ("Event Control Language") is the scripting VM that drives Gold Box
campaigns: dialogue, encounters, triggers, mission flags, everything.
Both DOS Buck Rogers games and the Genesis port of Countdown to Doomsday
run it -- see docs/re_notes.md.

Instruction encoding
--------------------
    u8   opcode
    N    arguments, where N is fixed per opcode
    ...  optionally, a variable-length tail of arguments whose count comes
         from one of the fixed arguments (menus, ON_GOTO jump tables)

Argument encoding -- a type byte followed by a payload:

    type  size      meaning
    0x00  1 byte    immediate byte
    0x01  2 bytes   memory address
    0x02  2 bytes   immediate short
    0x03  2 bytes   memory address (short)
    0x04  4 bytes   immediate int
    0x05  2 bytes   memory address
    0x80  variable  inline string, 6-bit packed
    0x81  2 bytes   string at a memory address

Strings pack four 6-bit characters into three bytes. A 6-bit value below
0x20 maps to ASCII value + 0x40, giving the run '@' 'A'..'Z' '[' '\' ']'
'^' '_'; values 0x20-0x3F are literal ASCII.

Opcode table and argument counts cross-checked against
farmboy0/ssi-engine (GPLv3, read as documentation -- no code copied).
"""

import struct

# (name, arg_count, dynamic_arg_source_index)
# Where an opcode number has several forms, the Buck Rogers variant is used;
# these come from the game configs shipped with ssi-engine.
OPCODES = {
    0x00: ("EXIT", 0, None),              0x01: ("GOTO", 1, None),
    0x02: ("GOSUB", 1, None),             0x03: ("COMPARE", 2, None),
    0x04: ("ADD", 3, None),               0x05: ("SUBTRACT", 3, None),
    0x06: ("DIVIDE", 3, None),            0x07: ("MULTIPLY", 3, None),
    0x08: ("RANDOM", 2, None),            0x09: ("WRITE_MEM", 2, None),
    0x0A: ("LOAD_CHAR", 1, None),         0x0B: ("LOAD_MON", 3, None),
    0x0C: ("SPRITE_START", 4, None),      0x0D: ("SPRITE_ADVANCE", 0, None),
    0x0E: ("PICTURE", 1, None),           0x0F: ("INPUT_NUMBER", 2, None),
    0x10: ("INPUT_STRING", 2, None),      0x11: ("PRINT", 1, None),
    0x12: ("PRINT_CLEAR", 1, None),       0x13: ("RETURN", 0, None),
    0x14: ("COMPARE_AND", 4, None),       0x15: ("MENU_VERTICAL", 3, 2),
    0x16: ("IF_EQUALS", 0, None),         0x17: ("IF_NOT_EQUALS", 0, None),
    0x18: ("IF_LESS", 0, None),           0x19: ("IF_GREATER", 0, None),
    0x1A: ("IF_LESS_EQUALS", 0, None),    0x1B: ("IF_GREATER_EQUALS", 0, None),
    0x1C: ("CLEAR_MON", 0, None),         0x1D: ("PARTY_STRENGTH", 1, None),
    0x1E: ("PARTY_CHECK", 6, None),       0x1F: ("SPACE_COMBAT", 4, None),
    0x20: ("NEW_ECL", 1, None),           0x21: ("LOAD_AREA_MAP", 3, None),
    0x22: ("PARTY_SKILL_CHECK", 3, None), 0x23: ("SKILL_CHECK", 3, None),
    0x24: ("COMBAT", 0, None),            0x25: ("ON_GOTO", 2, 1),
    0x26: ("ON_GOSUB", 2, 1),             0x27: ("TREASURE", 2, 1),
    0x28: ("ROB", 3, None),               0x29: ("INPUT_RETURN", 0, None),
    0x2A: ("COPY_MEM", 3, None),          0x2B: ("MENU_HORIZONTAL", 2, 1),
    0x2C: ("INPUT_YES_NO", 0, None),      0x2D: ("CALL", 1, None),
    0x2E: ("DAMAGE", 5, None),            0x2F: ("AND", 3, None),
    0x30: ("OR", 3, None),                0x31: ("SELECT_ACTION", 2, 1),
    0x32: ("FIND_ITEM", 1, None),         0x33: ("PRINT_RETURN", 0, None),
    0x34: ("CLOCK", 2, None),             0x35: ("WRITE_MEM_BASE_OFF", 3, None),
    0x36: ("NPC_ADD", 2, None),           0x37: ("LOAD_AREA_DECO", 3, None),
    0x38: ("PROGRAM", 1, None),           0x39: ("WHO", 1, None),
    0x3A: ("DELAY", 0, None),             0x3B: ("SPELL", 3, None),
    0x3C: ("COPY_PROTECTION", 1, None),   0x3D: ("CLEAR_BOX", 0, None),
    0x3E: ("NPC_REMOVE", 0, None),        0x3F: ("LOGBOOK_ENTRY", 2, None),
    0x40: ("DESTROY_ITEM", 1, None),      0x41: ("GIVE_EXP", 2, None),
    0x42: ("STOP_MOVE", 0, None),         0x43: ("SOUND_EVENT", 1, None),
    0x44: ("UNKNOWN_44", 0, None),        0x45: ("RANDOM0", 2, None),
    0x46: ("FOR_START", 2, None),         0x47: ("FOR_REPEAT", 0, None),
    0x48: ("UNKNOWN_48", 1, None),        0x49: ("UNKNOWN_49", 6, None),
    0x4A: ("UNKNOWN_4A", 0, None),        0x4B: ("UNKNOWN_4B", 1, None),
    0x4C: ("PICTURE2", 2, None),
}

ARG_SIZE = {0x00: 1, 0x01: 2, 0x02: 2, 0x03: 2, 0x04: 4, 0x05: 2, 0x81: 2}


class EclError(Exception):
    pass


def unpack_string(data: bytes) -> str:
    """Expand 6-bit packed characters: AAAAAABB BBBBCCCC CCDDDDDD."""
    out = []
    state, last = 1, 0
    for byte in data:
        if state == 1:
            vals, state = [(byte >> 2) & 0x3F], 2
        elif state == 2:
            vals, state = [((last << 4) | (byte >> 4)) & 0x3F], 3
        else:
            vals, state = [((last << 2) | (byte >> 6)) & 0x3F, byte & 0x3F], 1
        for v in vals:
            if v:
                out.append(chr(v + 0x40) if v < 0x20 else chr(v))
        last = byte
    return "".join(out)


class Argument:
    __slots__ = ("type", "size", "value")

    def __init__(self, type_, size, value):
        self.type, self.size, self.value = type_, size, value

    @property
    def is_memory(self):
        return self.type != 0x80 and (self.type & 0x01) > 0

    @property
    def is_string(self):
        return (self.type & 0x80) > 0

    def __str__(self):
        if self.type == 0x80:
            return '"%s"' % self.value
        if self.type == 0x81:
            return "str[0x%04X]" % self.value
        if self.is_memory:
            return "[0x%04X]" % self.value
        return str(self.value)


def parse_argument(data: bytes, pos: int) -> Argument:
    if pos >= len(data):
        raise EclError("ran off the end of the block reading an argument")
    type_ = data[pos]
    if type_ == 0x80:
        length = data[pos + 1]
        return Argument(type_, 2 + length,
                        unpack_string(data[pos + 2:pos + 2 + length]))
    if type_ not in ARG_SIZE:
        raise EclError("unknown argument type 0x%02X at 0x%04X" % (type_, pos))
    size = ARG_SIZE[type_]
    raw = data[pos + 1:pos + 1 + size]
    if len(raw) < size:
        raise EclError("truncated argument at 0x%04X" % pos)
    if size == 1:
        value = raw[0]
    elif size == 2:
        value = struct.unpack("<H", raw)[0]
    else:
        value = struct.unpack("<I", raw)[0]
    return Argument(type_, 1 + size, value)


class Instruction:
    __slots__ = ("offset", "size", "opcode", "name", "args", "dyn_args")

    def __init__(self, offset, size, opcode, name, args, dyn_args):
        self.offset, self.size = offset, size
        self.opcode, self.name = opcode, name
        self.args, self.dyn_args = args, dyn_args

    def __str__(self):
        parts = [str(a) for a in self.args]
        if self.dyn_args:
            parts.append("{" + ", ".join(str(a) for a in self.dyn_args) + "}")
        return "%-20s %s" % (self.name, ", ".join(parts))


def parse_instruction(data: bytes, pos: int) -> Instruction:
    start = pos
    opcode = data[pos]
    pos += 1
    if opcode not in OPCODES:
        raise EclError("unknown opcode 0x%02X at 0x%04X" % (opcode, start))
    name, argc, dyn_index = OPCODES[opcode]

    args = []
    for _ in range(argc):
        arg = parse_argument(data, pos)
        args.append(arg)
        pos += arg.size

    dyn_args = []
    if dyn_index is not None and dyn_index < len(args):
        count = args[dyn_index].value
        if not isinstance(count, int) or count > 64:
            raise EclError("implausible dynamic argument count %r at 0x%04X"
                           % (count, start))
        for _ in range(count):
            arg = parse_argument(data, pos)
            dyn_args.append(arg)
            pos += arg.size

    return Instruction(start, pos - start, opcode, name, args, dyn_args)


def disassemble(block: bytes, start: int = 0):
    """
    Linearly decode instructions from `start`.

    Returns (instructions, stop_offset, error). ECL blocks interleave code
    and data, so a clean stop partway through a block is normal, not a bug.
    """
    # Blocks may begin with a 5000 (0x1388) marker.
    if start == 0 and len(block) >= 2 and struct.unpack_from("<H", block, 0)[0] == 5000:
        start = 2

    instructions = []
    pos = start
    while pos < len(block):
        try:
            ins = parse_instruction(block, pos)
        except EclError as exc:
            return instructions, pos, str(exc)
        instructions.append(ins)
        pos += ins.size
    return instructions, pos, None


CODE_BASE = 0x8000   # ECL blocks are addressed from 0x8000 (ssi-engine: code.base)

# An ECL block opens with five instructions -- one per engine event hook.
# Each is normally a GOTO to the real handler, so these five give us the
# entry points for a proper reachability walk.
EVENT_HOOKS = ("onMove", "onSearchLocation", "onRest", "onRestInterruption", "onInit")

_JUMPS = {"GOTO", "GOSUB", "ON_GOTO", "ON_GOSUB"}
# Instructions after which control does not fall through.
_TERMINAL = {"EXIT", "RETURN", "GOTO", "ON_GOTO"}


def code_start(block: bytes) -> int:
    """Offset of the event-hook header (past the 5000 marker, if present)."""
    if len(block) >= 2 and struct.unpack_from("<H", block, 0)[0] == 5000:
        return 2
    return 0


def parse_header(block: bytes):
    """
    Decode the five event-hook instructions at the head of a block.

    Returns (hooks, offset_after_header) where hooks is a list of
    (name, Instruction) pairs. Raises EclError if the header is malformed.
    """
    pos = code_start(block)
    hooks = []
    for name in EVENT_HOOKS:
        ins = parse_instruction(block, pos)
        hooks.append((name, ins))
        pos += ins.size
    return hooks, pos


def _targets(ins, base):
    """
    Jump destinations named by an instruction, as block offsets.

    ECL code is addressed from 0x8000, and that address refers to the first
    byte *after* the 5000 marker -- so `base` (the marker size) is added back.
    """
    for arg in list(ins.args) + list(ins.dyn_args):
        if arg.is_memory and isinstance(arg.value, int):
            yield arg.value - CODE_BASE + base


def disassemble_block(block: bytes):
    """
    Reachability-based disassembly.

    Walks from each event hook and follows every jump target, rather than
    scanning linearly. ECL blocks interleave code and data, so a linear scan
    stops dead at the first data byte and under-reports badly; it also happily
    decodes data as instructions where it does not stop.

    Returns (instructions, entry_points, errors) with instructions keyed by
    block offset.
    """
    found = {}
    errors = []
    queue = []

    try:
        hooks, after_header = parse_header(block)
    except EclError as exc:
        return found, [], [(code_start(block), f"bad header: {exc}")]

    start = code_start(block)
    pos = start
    for _name, ins in hooks:
        found[pos] = ins
        pos += ins.size
        queue.extend(_targets(ins, start))
    entries = sorted({t for t in queue if 0 <= t < len(block)})
    queue = list(entries) + [after_header]

    while queue:
        pos = queue.pop()
        while 0 <= pos < len(block) and pos not in found:
            try:
                ins = parse_instruction(block, pos)
            except EclError as exc:
                errors.append((pos, str(exc)))
                break
            found[pos] = ins
            for t in _targets(ins, start):
                if 0 <= t < len(block) and t not in found:
                    queue.append(t)
            if ins.name in _TERMINAL:
                break
            pos += ins.size

    return found, entries, errors


def coverage(block: bytes, found: dict) -> float:
    """Fraction of the block claimed as instruction bytes."""
    return sum(i.size for i in found.values()) / len(block) if block else 0.0

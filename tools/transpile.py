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

import artmap
import ecl
import skillmap
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

    # Same opcode slot, same arity, and the Genesis name describes what the
    # DOS implementation does:
    #   SELECT_ACTION prints "WHAT DO YOU DO?" then a horizontal menu and
    #   stores the choice -- which is what WHMENU is for.
    "SELECT_ACTION": "WHMENU",
    "PICTURE2": "VIEW",
    "COPY_MEM": "GETABLE",
}

# CALL dispatches to a native routine by address, so it cannot be remapped by
# name. Buck Rogers uses exactly two, and the Genesis has dedicated opcodes
# for both -- which is unsurprising, since a console port would naturally
# promote a frequently-called native routine to its own opcode.
#
#   0x2DCB (150 sites) -- redraw the view and clear the current sprite
#   0xC01E  (11 sites) -- step one square forward in the facing direction
CALL_EXPANSION = {
    0x2DCB: ("REMOVEFIGURE", "UPDATEFRAME"),
    0xC01E: ("STEPFORWARD",),
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
# DOS variables that configure engine behaviour the Genesis arranges
# differently, and which therefore have no counterpart to map to.
#
# The DOS engine's own decompiler annotates 0x4BE7 and 0x4BE8 as configuring
# LOAD_AREA_DECO -- the opcode the Genesis calls LOADPIECES. The Genesis
# handler derives the same information from its argument instead:
#
#     03ADE  divu.w  #$3,d2        ; wallset index
#     03AE2  move.b  d2,$9AFB.w
#
# Writes to these are given inert storage rather than being dropped. Dropping
# them would change instruction counts and disturb the layout for no gain,
# and a write that lands somewhere harmless is easier to reason about than a
# missing one. Reads return whatever the script last wrote, which is the DOS
# behaviour anyway for a value the engine never consults.
INERT = (0x4BE7, 0x4BE8, 0x4BE9, 0x4BFB, 0x4BAB)

# Any engine-shared variable whose Genesis counterpart is not established
# also gets inert storage, rather than a plausible-looking guess.
#
# This reverses an earlier judgement. The argument for guessing was that an
# unmapped DOS address sign-extends into ROM, so the write vanishes silently
# -- worse, it seemed, than a wrong address failing visibly. That reasoning
# only holds if the wrong address is dead. It usually is not: a guess drawn
# from the engine-written/script-read set is by construction a LIVE engine
# variable, so a mistake corrupts real state instead of merely losing some.
#
# LAST_DUNGEON_X made the case concrete. It looked like 0x9BCB on adjacency
# grounds, but DOS only ever copies into it -- 30 writes, no immediates --
# while 0x9BCB is always written with constants {96, 0, 32}. Different
# behaviour, so the mapping was wrong, and applying it would have written
# garbage into whatever 0x9BCB actually controls.
#
# Inert storage degrades gracefully instead: scripts read back what they
# wrote, so logic among themselves still works, and only the engine's view
# is missing. That is a bounded, documented loss rather than corruption.
INERT_UNKNOWN = True

PROBABLE_MAP = {
    # The only non-scratch operand of LOAD_CHAR / LOADCHARACTER on each side,
    # 27 uses against 10. Scripts use it to walk the party.
    0x4CF6: 0x98EC,    # FOR_LOOP_COUNT

    # DUNGEON_VALUE distinguishes overland from dungeon. Both sides are
    # write-only from scripts -- 45 of 46 DOS uses and 31 of 31 Genesis --
    # and carry the same shape of value: a high bit set, plus 16.
    # DOS {132,129,128,16} against Genesis {130,80,16,0}.
    0x4BE6: 0x97DC,    # DUNGEON_VALUE
    # of the confirmed X/Y pair in DOS, and 0x9BCB is engine-written,
    # script-read, and write-only from scripts like its DOS counterparts.
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
    # The whole 0x7E00-0x7FFF region is one bank relocated by a constant
    # 0x1EF6. This is not inferred from a similarity score: four mappings
    # established independently and by different means all land on it.
    #
    #   INDEX_OF_SEL_PC     0x7EB1 -> 0x9DA7   read off the address resolver
    #   COMBAT_RESULT       0x7EC7 -> 0x9DBD   tested against 128 on both sides
    #   MOVEMENT_BLOCK      0x7EC9 -> 0x9DBF   255 in 63/63 and 57/57 uses
    #   TEMP_START          0x7F79 -> 0x9E6F   dominant AND/OR destination
    #
    # Two of those came from engine disassembly and two from script usage, so
    # the agreement is not an artefact of one method. COMBAT_MORALE_BASE
    # then falls out for free at 0x9DBC, writing {80, 90, 100} on both sides.
    #
    # The offset does NOT extend below 0x7E00: 0x7C00 + 0x1EF6 would be
    # 0x9AF6, which is DUNGEON_X, while the resolver places SEL_PC_START at
    # 0x9AFC. The character records were relocated separately.
    (0x7E00, 0x8000, 0x9CF6),      # combat, party and scratch bank
    (0x7C00, 0x7C4D, 0x9AFC),      # selected-character record (relocated separately)
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
        # CALL becomes one or more Genesis opcodes depending on which native
        # routine it targets, so it is handled before the ordinary name map.
        if ins.name == "CALL" and ins.args and ins.args[0].value in CALL_EXPANSION:
            for sub in CALL_EXPANSION[ins.args[0].value]:
                opcode, _argc = gen[sub]
                layout.setdefault(off, pos)
                pieces.append((off, opcode, []))
                pos += 1
            continue

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
        # The two engines number skills completely differently: DOS uses the
        # full 84-skill tabletop list 1-based, the Genesis 19 of its own.
        # The engine prints the name as string 0x54 + id, so an untranslated
        # id indexes past the skill names into unrelated text -- DOS 46
        # (Astrogation) came out as "career and" in play.
        is_skill = ins.name in ("PARTY_SKILL_CHECK", "SKILL_CHECK")
        # ON_GOTO/ON_GOSUB are jumps whose FIRST operand is not a target: it
        # is the selector variable the engine indexes the target list with.
        # Classifying operands by instruction rather than by position sent
        # it through jump rebasing, where it missed the layout and fell back
        # to GEN_BASE -- so every menu in the game read its choice from the
        # code base instead of from the variable the menu had just written.
        is_on = ins.name in ("ON_GOTO", "ON_GOSUB")
        # Matrix Cubed names art the Genesis cartridge does not carry, and an
        # unknown id crashes the picture loader rather than being ignored.
        # DOS names, not Genesis ones: PICTURE2 is what NAME_MAP turns into
        # VIEW. Keying this on "VIEW" meant the guard never fired for it.
        art_at = (0 if ins.name == "PICTURE" else
                  1 if ins.name == "PICTURE2" else None)
        mon_at = 0 if ins.name in ("LOAD_MON", "SPRITE_START") else None
        args = []
        for k, arg in enumerate(list(ins.args) + list(ins.dyn_args)):
            if mon_at == k and arg.type == 0x00 and arg.value < 0x80:
                new, replaced = artmap.monster(arg.value)
                if replaced:
                    report.append((off, "monster",
                                   f"{ins.name} 0x{arg.value:02X} -> 0x{new:02X}"))
                args.append(("imm", new))
                continue
            if art_at == k and arg.type == 0x00:
                if ins.name == "PICTURE":
                    new, replaced = artmap.picture(arg.value)
                else:
                    mode = ins.args[0].value if ins.args[0].type == 0x00 else None
                    new, replaced = artmap.view(mode, arg.value)
                if replaced:
                    report.append((off, "art",
                                   f"{ins.name} 0x{arg.value:02X} not in this ROM"))
                args.append(("imm", new))
                continue
            if is_skill and k == 0 and arg.type == 0x00:
                gid, exact = skillmap.translate(arg.value)
                if not exact:
                    report.append((off, "skill", f"{skillmap.DOS_NAMES.get(arg.value, arg.value)}"
                                                 f" -> {skillmap.GENESIS[gid]} (nearest fit)"))
                args.append(("imm", gid))
                continue
            if arg.type == 0x80:
                args.append(("str", pool.intern(str(arg.value))))
            elif arg.is_memory:
                # Only a jump's operands are code addresses, and not even
                # all of those -- see is_on above.
                if is_jump and not (is_on and k == 0):
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

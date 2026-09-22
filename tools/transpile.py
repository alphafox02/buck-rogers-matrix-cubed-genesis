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
import soundmap
import wallmap
import monstermap
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
    "SPACE_COMBAT": "SPACECOMBAT",
    "NEW_ECL": "NEWECL", "LOAD_AREA_MAP": "LOADFILES", "SKILL_CHECK": "SKILL",
    "PARTY_SKILL_CHECK": "PRINTSKILL", "ON_GOTO": "ONGOTO", "ON_GOSUB": "ONGOSUB",
    "MENU_HORIZONTAL": "HMENU", "INPUT_YES_NO": "GETYN", "FIND_ITEM": "FINDITEM",
    "PRINT_RETURN": "PRINTRETURN", "NPC_ADD": "ADDNPC",
    "LOAD_AREA_DECO": "LOADPIECES", "LOGBOOK_ENTRY": "JOURNAL",
    # The two opcode tables are the same engine's, numbered alike -- 0x40 is
    # DESTROY_ITEM/DESTROY, 0x41 GIVE_EXP/ADDEP, 0x43 SOUND_EVENT/SOUND,
    # 0x4C PICTURE2/VIEW. So the opcodes the DOS disassembler could not name
    # are not unknown, they are simply unnamed: the Genesis table has one at
    # the same number, with the same argument count, and the call sites agree.
    #
    #   0x44  before "<name> IS HEALED..." after writing the record  -> SAVECHARACTER
    #   0x48  around area changes                                    -> HIDEITEMS
    #   0x4A  after LOAD_MON, before "THE BARTENDER KICKS YOU OUT"   -> DUEL
    #   0x4B  19 uses, one byte operand                              -> STORE
    #   0x3E                                                         -> DUMP
    #   0x45                                                         -> HOWFAR
    #
    # That is 59 of the 62 instructions that were doing nothing.
    "UNKNOWN_44": "SAVECHARACTER", "UNKNOWN_48": "HIDEITEMS",
    "UNKNOWN_4A": "DUEL", "UNKNOWN_4B": "STORE",
    "NPC_REMOVE": "DUMP", "RANDOM0": "HOWFAR",
    # NOT mapped, on argument count. UNKNOWN_49 carries six operands where
    # the Genesis SKILLDAMAGE table says none, and WRITE_MEM_BASE_OFF three
    # where SAVETABLE says none. The call sites fit -- 0x49 follows "BONUS #
    # TO DAMAGE?" -- but if the handler really reads no operands then the
    # DOS ones would be executed as opcodes, and a wrong guess there is a
    # wild jump. Three instructions, both in the developer block. They keep
    # stepping over themselves until the handlers are read.
    "DESTROY_ITEM": "DESTROY", "GIVE_EXP": "ADDEP",
    "CLEAR_BOX": "CLEARBOX", "FOR_START": "FOR",
    # SPELL -> SPELLS, COPY_PROTECTION -> PROTECT and PARTY_CHECK ->
    # CHECKPARTY are deliberately NOT mapped, though the slots line up. All
    # three Genesis handlers are `bra.w $4022`, and 0x04022 prints
    # "command not supported!" and stops. Mapping onto them turns an
    # instruction that works in DOS into a hard error, where the stub path
    # merely steps over it.
    "FOR_REPEAT": "ENDFOR", "SOUND_EVENT": "SOUND",
    "CLOCK1": "CLOCK",

    # STOP_MOVE ends the event; it does not wait for a button. It used to be
    # mapped to CONTINUE, which does the opposite -- it waits and then runs
    # on -- so every script that said "if the player says no, stop" ran the
    # yes branch anyway, and every script that ended with STOP_MOVE fell into
    # whatever routine happened to be next. The first one caught was the
    # bundle of papers on the opening dock: answer either way and the script
    # walked on into the teleport tail below it, whose last instruction is a
    # GOTO back to the question. An unbreakable loop, from one wrong name.
    #
    # It is opcode 0x42 in both engines, and the two uses profile the same
    # way. Counting how often each is the last instruction of a basic block
    # -- the next offset is a jump target, or nothing decodes there:
    #
    #     Matrix Cubed  STOP_MOVE      407 of 532   76%   127 guarded by an IF
    #     Countdown     ENCEXIT        374 of 431   87%    51 guarded by an IF
    #     Matrix Cubed  INPUT_RETURN    90 of 1784   5%    51 guarded by an IF
    #
    # A terminator, like RETURN (78% / 84%), and nothing like INPUT_RETURN.
    "STOP_MOVE": "ENCEXIT",
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
# Every opcode named here must take ZERO arguments, because the expansion
# emits the opcode byte alone. `UPDATEFRAME` used to be in the first entry
# and takes one: the interpreter then read the NEXT instruction as its
# argument, which at the shop door was the `PICTURE` of the shopkeeper. The
# portrait never drew, the program counter desynced, and leaving the shop
# ended in the engine's own "Bad ECL address". 150 sites called it.
#
# `UPDATEFRAME` alone. Three arrangements were tried against the shop, whose
# exit path is `PICTURE 255` (clear the window), `CALL 0x2DCB` (redraw),
# `CONTINUE`:
#
#   REMOVEFIGURE + UPDATEFRAME, no argument -- the interpreter reads the
#     NEXT instruction as the argument. At the shop door that was the
#     shopkeeper's `PICTURE`, so no portrait drew and the program counter
#     desynced into "Bad ECL address".
#   REMOVEFIGURE alone -- portrait fixed, screen black on exit.
#   REMOVEFIGURE + UPDATEFRAME with an argument -- still black.
#
# `REMOVEFIGURE` is the problem. It wipes the whole display list, and then
# `UPDATEFRAME` indexes `$b0b2 - 1`, which is -1:
#
#     0C134: clr.w $b0b2.w     ; REMOVEFIGURE: display entries = 0
#     0C138: clr.w $b016.w     ;               combatants = 0
#     0C13C: bsr.w $c3f0       ;               redraw the board
#
#     0C14C: move.w $b0b2.w, d0   ; UPDATEFRAME: the LAST display entry
#     0C150: subq.w #$1, d0
#     0C152: mulu.w #$12, d0
#     0C176: clr.b  $8(a2)        ; clears the sprite
#
# And `UPDATEFRAME` on its own is already what the DOS call describes --
# "redraw the view and clear the current sprite" -- because `clr.b $8(a2)`
# is that clear. Zero is the argument: no flip, frame 0.
#   (4) nothing at all -- 0x2DCB left out, so it falls through to the stub
#       path and becomes a GOTO to the next instruction: a real opcode the
#       engine understands, which steps over and executes nothing. Stock
#       Countdown never puts REMOVEFIGURE or UPDATEFRAME next to a PICTURE
#       anyway; its idiom is plain `VIEW / PICTURE / PRINTCLEAR / CONTINUE`.
#   (5) `VIEW 0, 0xFF` -- back to the ordinary game screen with no picture.
#       Driving the shop under tools/play.py and probing the failure showed
#       the screen is not black at all: it is a full-width text window with
#       the default space picture, i.e. the wrong LAYOUT. The party position
#       updates correctly on exit -- (3,5) to (3,4) -- so the script runs
#       fine and only the view is wrong. VIEW is what picks the layout, and
#       `VIEW 0, 0xFF` is the idiom stock Countdown and tools/bootstub.py
#       both use to get back to the ordinary screen.
CALL_EXPANSION = {
    0x2DCB: (("VIEW", (("imm", 0), ("imm", 0xFF))),),
    0xC01E: (("STEPFORWARD", ()),),
}


def genesis_opcodes():
    """Genesis mnemonic -> (opcode number, fixed argument count)."""
    table = G.load_opcodes()
    return {name: (op, argc) for op, (name, argc) in table.items()}


STUB_OPCODE = 0xFF          # outside the valid 0x00-0x5D range

# The widest label sets stock Countdown ever gives each menu opcode. Past
# these the labels run off the line and wrap back over themselves.
WHMENU_BUDGET = 27
HMENU_BUDGET = 35

# Leading words that carry no meaning once the choice is on screen. Dropping
# one keeps the informative half: "CALL SECURITY" reads fine as "SECURITY",
# where truncating from the right would give "CALL SECUR".
FILLER = ("CALL", "HELP", "AID", "GO", "GO TO", "USE", "TRY", "TAKE", "ASK",
          "LOOK", "TALK", "TALK TO", "MAKE", "GIVE", "SHOW", "OPEN", "READ")


def _width(labels):
    return sum(len(x) for x in labels) + len(labels) - 1


def fit_labels(labels, budget):
    """Shorten a label set until it fits, longest first.

    Drops a leading filler word where there is one, since that keeps the
    part that distinguishes the choice, and truncates only as a last resort.
    """
    out = list(labels)
    while _width(out) > budget:
        k = max(range(len(out)), key=lambda i: len(out[i]))
        words = out[k].split()
        if len(words) > 1 and words[0] in FILLER:
            out[k] = " ".join(words[1:])
        elif len(words) > 1:
            out[k] = " ".join(words[:-1])
        elif len(out[k]) > 3:
            out[k] = out[k][:-1]
        else:
            break
    return out


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
    if kind in ("code", "var", "skip"):
        return bytes([0x01]) + struct.pack("<H", value & 0xFFFF)
    if kind == "strptr":
        # Type 0x81 is "the string is at this address", not "this is a
        # variable". Both engines read it the same way. Collapsing it to
        # 0x01 made PRINT_CLEAR str[0x7C00] -- print the loaded character's
        # name -- render the record as if it were a number.
        return bytes([0x81]) + struct.pack("<H", value & 0xFFFF)
    if value <= 0xFF:
        return bytes([0x00, value])
    if value <= 0xFFFF:
        return bytes([0x02]) + struct.pack("<H", value)
    return bytes([0x04]) + struct.pack("<I", value)


# Engine-shared variables whose Genesis counterpart is established.
VARIABLE_MAP = {
    0x4BF2: 0x97E8,    # LAST_ECL, the current area
    # X is 0x9AF7 and Y is 0x9AF6 -- see the note in tools/bootstub.py. The
    # square lookup is d4*16 + d3 with d3 from 0x9AF7, and both games store
    # maps row major, so d3 is X.
    0xC04B: 0x9AF7,    # DUNGEON_X
    0xC04C: 0x9AF6,    # DUNGEON_Y
    0xC04D: 0x9AFA,    # DUNGEON_DIR
    # MAP_WALL_TYPE. The bank settles this one: 0xC04B/0xC04C/0xC04D/0xC04F
    # are X, Y, facing and the square's event byte, and all four are already
    # established against 0x9AF7/0x9AF6/0x9AFA/0x9AF9. 0xC04E is the only
    # one left and 0x9AF8 is the only slot left.
    #
    # It used to point at 0x97AD, on the grounds that Countdown's own scripts
    # read that the way Matrix Cubed reads 0xC04E and both top out at 12.
    # They do -- but the two are computed differently and only one of them
    # can work here. 0x97AD comes from 0x0CCEA, which classifies the DRAWN
    # tiles against the loaded wall set's piece table; Matrix Cubed's areas
    # never select a set that has one, so it reads 0 forever and every gate
    # on it fails. 0x9AF8 comes from 0x04244, which reads the wall nibble in
    # the facing direction straight out of the map planes at 0xB5A4/0xB6A4 --
    # our own injected geometry, carrying Matrix Cubed's own wall codes,
    # which run 0-14 against the 0-12 the scripts compare.
    0xC04E: 0x9AF8,    # MAP_WALL_TYPE
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


# The Genesis text window is four lines of thirty-five columns, greedily
# word wrapped, and the engine does not clip: it writes a whole string into
# the window and runs off the end back to the start, so anything longer
# overwrites its own opening.
#
# Two screenshots pinned it exactly. Dr Romney's 156-character introduction
# wrapped to
#
#     A MAN CARRYING A BUNDLE OF PAPERS   (33)
#     RUSHES UP TO YOU. HE GRABS YOUR ARM (35)
#     DESPERATELY. 'I AM DR. ROMNEY.      (30)
#     PLEASE HELP ME GET TO THE SUN KING. (35)
#
# consuming 136 characters and leaving 19 -- and 19 is exactly what landed
# on top of "A MAN CARRYING A BU". The next line of the same scene, 142
# characters, wraps to 35/35/32/32 = 137 and leaves 4, and exactly 4 --
# "YOU." -- appeared over "'TAK".
#
# So the limit is not a character count. It depends on where the words fall,
# which is why a flat 137 was right for one string and wrong for the next.
COLUMNS, LINES = 35, 4

# What to budget for a string operand whose length is not known until the
# game runs -- type 0x81, almost always a character or a place name.
VARIABLE_TEXT = 12


def _wrap(text):
    """Greedy word wrap, the way the window does it."""
    lines, cur = [], ""
    for word in text.split(" "):
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= COLUMNS:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
        while len(cur) > COLUMNS:          # a single word wider than the line
            lines.append(cur[:COLUMNS])
            cur = cur[COLUMNS:]
    if cur:
        lines.append(cur)
    return lines


def _split(text):
    """Break a string into screenfuls of LINES wrapped lines."""
    lines = _wrap(text)
    if len(lines) <= LINES:
        return [text]
    return [" ".join(lines[i:i + LINES]) for i in range(0, len(lines), LINES)]


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

    # Data tables inside the block.
    #
    # COPY_MEM's first operand is a code-space address, and it does not point
    # at code: it points at a table of bytes sitting between routines --
    #
    #     01E86  COPY_MEM  [0xA088], [0x7F7A], [0x4BB7]
    #     01E9C  <0x01 01 01 02 02 02 02 02 02 19 19 19 19 ...>
    #
    # Two things went wrong with those. The decoder walks into the table and
    # reads it as instructions, which is where the "lost jumps" came from --
    # phantom GOTOs to 0x0101 and 0x0303, addresses no code ever had. And
    # because COPY_MEM is not a jump, its operand went through the variable
    # map instead of being rebased, so after relocation it addressed
    # whatever now sat at the old offset. 121 of them, across eight blocks.
    #
    # A table runs from the address COPY_MEM names to the next offset real
    # code branches to. Emitting those bytes verbatim keeps the table intact
    # AND keeps its length, so everything after it lands where the layout
    # says.
    jump_targets = set()
    data_starts = set()
    for ins in found.values():
        is_j = ins.name in ecl._JUMPS
        on = ins.name in ("ON_GOTO", "ON_GOSUB")
        for k, a in enumerate(list(ins.args) + list(ins.dyn_args or [])):
            v = getattr(a, "value", None)
            if getattr(a, "type", None) != 0x01 or v is None:
                continue
            if not DOS_BASE <= v < 0xC000:
                continue
            at = v - DOS_BASE + marker
            if is_j and not (on and k == 0):
                jump_targets.add(at)
            elif ins.name == "COPY_MEM" and k == 0:
                data_starts.add(at)

    data = {}
    for start in sorted(data_starts):
        if start in jump_targets or start >= len(block):
            continue
        after = [t for t in sorted(jump_targets) if t > start]
        end = min(after[0], len(block)) if after else len(block)
        # Stop at the next table too, so neighbours do not swallow each other.
        nxt = [d for d in sorted(data_starts) if d > start]
        if nxt:
            end = min(end, nxt[0])
        if end > start:
            data[start] = end
    covered = set()
    for a, b2 in data.items():
        covered.update(range(a, b2))

    # A table's address need not be somewhere the decoder ever walked -- most
    # are read by COPY_MEM and branched to by nothing -- so the layout pass
    # has to visit table starts as well as decoded instructions, or their
    # pointers have nothing to rebase onto.
    # Where a run of print instructions overflows the window.
    #
    # _split handles one string that is too long. It does not help when the
    # text is BUILT from several instructions, which is how the engine does
    # anything with a variable in it:
    #
    #     00D25  PRINT_CLEAR  "THE TELLTALE ON THE DOOR READS,"
    #     00D40  PRINT_RETURN x2
    #     00D42  PRINT        "BERTH " + the berth letter
    #     00D56  PRINT_RETURN, PRINT "SHIP:  " ... and the homeport
    #
    # Five lines into a four-line window, so the last one lands back on the
    # first and the player reads "HOMEPORT: DUKE'S HILLOR READS,". DOS has a
    # taller box and never had to care.
    #
    # The window is simulated across each run: PRINT_CLEAR resets it, PRINT
    # appends and wraps, PRINT_RETURN starts a line, and anything else ends
    # the run. Where the next instruction would push past the fourth line it
    # gets a CONTINUE in front of it, and a PRINT there becomes a
    # PRINT_CLEAR so the next screen starts empty. A PRINT_RETURN at a break
    # is dropped, since a fresh window is already at the left margin.
    #
    # A string operand of unknown length -- type 0x81, "print what is at this
    # address", almost always a character or place name -- is budgeted at
    # VARIABLE_TEXT characters.
    #
    # Except that it is often not unknown at all. The engine's idiom for
    # "<name>, followed by a fixed phrase" is to stash the phrase in a string
    # variable and print the two in turn:
    #
    #     PRINT_CLEAR  "A DISEMBODIED VOICE ECHOES THROUGH THE HALL, '"
    #     WRITE_MEM    ", PLEASE REPORT TO THE NEAREST COURTESY CONSOLE.", [s]
    #     PRINT        [the character's name]
    #     PRINT        [s]
    #
    # Budgeting that 48-character phrase at twelve under-counted the run by
    # three lines, so no page break went in and the tannoy on the opening
    # dock printed over its own PRESS C prompt. Where the phrase is written
    # as a literal its real length is known, so it is remembered against the
    # variable and used when that variable is printed. A WRITE_MEM of this
    # shape also no longer ENDS the run, which it used to, cutting the
    # simulation off before the two PRINTs it exists to set up.
    # Instructions that touch neither the window nor the flow of text. The
    # simulation used to end its run at any of these, which is wrong: the
    # engine's window keeps accumulating across them. De Sade's payment
    # speech on the opening dock is built as
    #
    #     PRINT_CLEAR  "CHANCELLOR DE SADE SHAKES YOUR HAND GRACIOUSLY. '"
    #     AND / IF_NOT_EQUALS
    #     PRINT        "WITH BERKELEY DEAD, ... NEVERTHELESS,"
    #     IF_EQUALS
    #     PRINT        "IT IS GOOD THAT YOU WERE HERE, ..."
    #     PRINT        " HERE IS PAYMENT FOR YOUR SERVICES.'"
    #
    # and the AND ended the run before a single PRINT was counted, so no page
    # break went in. Either branch overflows: 180 characters wraps to six
    # lines and 145 to five, against a window of four, and the extra lines
    # land back on the first two. The player reads "NEVERTHELESS, HERE IS
    # PAYMENT FORND / YOUR SERVICES.'TH BERKELEY DEAD" -- the ND and TH being
    # what is left of HAND and WITH underneath.
    WINDOW_TRANSPARENT = {
        "AND", "OR", "COMPARE", "ADD", "SUB", "WRITE_MEM", "SAVE",
        "IF_EQUALS", "IF_NOT_EQUALS", "IF_LESS", "IF_GREATER",
        "IF_LESS_EQUALS", "IF_GREATER_EQUALS",
    }

    breaks = {}
    _line = _col = 0
    _active = False
    _known = {}
    for _off in sorted(found):
        _ins = found[_off]
        _n = _ins.name
        _args = list(_ins.args)
        if _n == "WRITE_MEM" and len(_args) == 2 \
                and getattr(_args[0], "type", None) == 0x80 \
                and getattr(_args[1], "type", None) in (0x01, 0x81):
            _known[_args[1].value] = len(str(_args[0].value))
            continue                       # sets a phrase up; prints nothing
        _t = None
        for _a in _args:
            if getattr(_a, "type", None) == 0x80:
                _t = str(_a.value)
            elif getattr(_a, "type", None) == 0x81:
                _t = "x" * _known.get(_a.value, VARIABLE_TEXT)
        if _n == "PRINT_CLEAR":
            _active, _line, _col = True, 0, 0
            if _t is not None:
                _rows = _wrap(_split(_t)[0]) or [""]
                _line, _col = len(_rows) - 1, len(_rows[-1])
            continue
        if not _active:
            continue
        if _n == "PRINT_RETURN":
            if _line + 1 >= LINES:
                breaks[_off] = "drop"
                _active = False
            else:
                _line += 1
                _col = 0
            continue
        if _n == "PRINT" and _t is not None:
            _rows = _wrap(_t) or [""]      # an empty string adds nothing
            _need = _line + len(_rows) - 1 + (1 if _col + len(_rows[0]) > COLUMNS else 0)
            if _need >= LINES:
                breaks[_off] = "clear"
                _line, _col = len(_rows) - 1, len(_rows[-1])
            else:
                _line = _need
                _col = _col + len(_rows[0]) if len(_rows) == 1 else len(_rows[-1])
            continue
        if _n in WINDOW_TRANSPARENT:
            continue
        _active = False

    order = sorted(set(found) | set(data))

    # `PICTURE 255` followed by `CALL 0x2DCB` has to come out the other way
    # round. DOS reads "blank the picture window, then redraw the view"; the
    # Genesis engine cannot run it in that order, because the redraw is also
    # what RESETS the sprite attribute table (VIEW -> 0x0860E -> 0x09222),
    # and PICTURE appends to it. Leaving the shop the party is already using
    # 73 of the hardware's 80 sprites, the default picture's animation wants
    # nine more, and the last two land past the end of the table -- which is
    # the blank UI tile at VRAM 0xEE80. Every empty cell on the screen then
    # drew as coloured noise: the text box, and the right-hand column, for
    # the rest of the session, because nothing ever writes that tile again.
    #
    # Hoisting the redraw in front of the PICTURE is exactly stock
    # Countdown's own idiom -- VIEW, PICTURE, PRINTCLEAR, CONTINUE -- and the
    # sprite table is back at the start when the picture asks for its nine.
    redraw_first = {}
    for _off, _ins in found.items():
        if _ins.name != "PICTURE":
            continue
        _next_off = _off + _ins.size
        _next = found.get(_next_off)
        if _next is None or _next.name != "CALL" or not _next.args:
            continue
        _exp = CALL_EXPANSION.get(_next.args[0].value)
        if not _exp or _exp[0][0] != "VIEW":
            continue
        if _next_off in jump_targets:
            # Something branches between the two, so the pair is not an
            # idiom and reordering it would change where that branch lands.
            continue
        redraw_first[_off] = (_next_off, _exp)
    hoisted = {call_off for call_off, _ in redraw_first.values()}
    redraw_pos = {}

    # COMBAT leaves the display DISABLED and the script has to switch it back
    # on. The engine blanks through 0x085D6 -- `move.w #$8124,(a4)`, VDP
    # register 1 with the display bit clear -- and only 0x0860E turns it on
    # again, which VIEW reaches and nothing else the scripts use does. Read
    # out of a savestate across the spoils screen:
    #
    #     at the shop door   reg1=64  display on
    #     spoils screen      reg1=64  display on
    #     one button later   reg1=24  display OFF, and it stays off
    #
    # Stock Countdown never notices because its scripts follow COMBAT with
    # EXIT (15 sites) or ENCEXIT (6), both of which end the event and let the
    # walk loop rebuild the screen. Matrix Cubed's carry straight on --
    # `COMBAT / COMPARE / IFLT / GOTO` is its commonest shape, 29 sites --
    # because the DOS engine restored the view by itself. Winning the fight
    # for Romney on the opening dock left a black screen with the music still
    # playing, and the script running behind it.
    #
    # So COMBAT gets a redraw unless the next instruction is already one.
    restore_after = set()
    wallsel = {}
    for _off, _ins in found.items():
        if _ins.name != "COMBAT":
            continue
        _next = found.get(_off + _ins.size)
        if _next is None or _next.name in ("EXIT", "STOP_MOVE"):
            continue
        if _next.name == "CALL" and _next.args \
                and _next.args[0].value in CALL_EXPANSION:
            continue
        restore_after.add(_off)

    # Pass 1: lay out, learning each instruction's new offset.
    layout, pos = {}, 0
    pieces = []
    for off in order:
        if off in data:
            raw = bytes(block[off:data[off]])
            layout[off] = pos
            pieces.append((off, None, raw, len(raw)))
            pos += len(raw)
            report.append((off, "data",
                           f"{len(raw)} bytes kept verbatim (a COPY_MEM table)"))
            continue
        if off in covered:
            continue                       # inside a table, not an instruction
        brk = breaks.get(off)
        if brk:
            cont, _ = gen["CONTINUE"]
            layout.setdefault(off, pos)
            pieces.append((off, cont, [], 1))
            pos += 1
            report.append((off, "window", f"page break before {found[off].name}"))
            if brk == "drop":
                continue
        ins = found[off]
        if off in hoisted:
            # Already emitted, in front of the PICTURE just before it.
            layout.setdefault(off, pos)
            continue
        if off in redraw_first:
            redraw_pos[off] = pos
            for sub, subargs in redraw_first[off][1]:
                opcode, argc = gen[sub]
                if argc != len(subargs):
                    raise SystemExit(
                        f"CALL_EXPANSION gives {sub} {len(subargs)} arguments "
                        f"but the Genesis opcode takes {argc}")
                size = 1 + sum(len(_encode_arg(k, v)) for k, v in subargs)
                pieces.append((off, opcode, list(subargs), size))
                pos += size
            report.append((off, "redraw",
                           f"{sub} hoisted in front of PICTURE so the redraw "
                           f"resets the sprite table first"))
        # CALL becomes one or more Genesis opcodes depending on which native
        # routine it targets, so it is handled before the ordinary name map.
        if ins.name == "CALL" and ins.args and ins.args[0].value in CALL_EXPANSION:
            for sub, subargs in CALL_EXPANSION[ins.args[0].value]:
                opcode, argc = gen[sub]
                if argc != len(subargs):
                    raise SystemExit(
                        f"CALL_EXPANSION gives {sub} {len(subargs)} arguments "
                        f"but the Genesis opcode takes {argc}; the interpreter "
                        f"would read the next instruction as its argument")
                size = 1 + sum(len(_encode_arg(k, v)) for k, v in subargs)
                layout.setdefault(off, pos)
                pieces.append((off, opcode, list(subargs), size))
                pos += size
            continue

        # Set BEFORE the lookup, so the stub branch below can override them.
        # These two lines used to sit AFTER it and unconditionally undid
        # `stub = True`, so `if stub:` at the emit site was never once taken
        # and every stubbed opcode became a GOTO carrying the original
        # instruction's arguments -- `CALL 0x2DCB` became `GOTO 0x2DCB`, a
        # wild jump into nothing. That is the very failure the comment below
        # says was fixed; the fix had been dead code.
        stub = False
        is_jump = ins.name in ecl._JUMPS

        name = NAME_MAP.get(ins.name, ins.name)
        if brk == "clear":
            name = "PRINTCLEAR"             # start the new screen empty
        if name in gen:
            opcode, _ = gen[name]
        else:
            # Emit a GOTO over the instruction rather than dropping it.
            #
            # Dropping it would remove its offset from the layout and strand
            # every jump that targets it, turning one untranslatable opcode
            # into dozens of broken branches. But the old stub -- opcode 0xFF,
            # chosen because it is outside the 94-opcode range and therefore
            # unmistakable -- was worse than useless, because the dispatch
            # does not bounds check:
            #
            #     03346: move.b (a2)+, d1      ; any byte, 0..255
            #     03356: asl.w  #$1, d1
            #     03358: lea.l  $336e.l, a3    ; 94 entries, ending 0x342A
            #     0335E: move.w (a3, d1.w), d1
            #     03362: jsr    (a3, d1.w)
            #
            # 0xFF reads a word from 0x356C -- inside the handler code, well
            # past the table -- and jumps through it. Every stub was a wild
            # jump waiting for a branch to reach it, and there are 62.
            #
            # A GOTO to the next instruction is a real opcode the engine
            # understands, and it steps over the arguments without executing
            # anything. It needs four bytes, so a shorter instruction grows;
            # pass 1 accounts for that and every jump still lands correctly.
            report.append((off, ins.name, "no Genesis counterpart"))
            opcode = gen["GOTO"][0]
            is_jump = False
            stub = True
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
        overflow = []
        # Matrix Cubed names art the Genesis cartridge does not carry, and an
        # unknown id crashes the picture loader rather than being ignored.
        # DOS names, not Genesis ones: PICTURE2 is what NAME_MAP turns into
        # VIEW. Keying this on "VIEW" meant the guard never fired for it.
        art_at = (0 if ins.name == "PICTURE" else
                  1 if ins.name == "PICTURE2" else None)
        mon_at = 0 if ins.name in ("LOAD_MON", "SPRITE_START") else None
        snd_at = 0 if ins.name == "SOUND_EVENT" else None
        wall_at = 0 if ins.name == "LOAD_AREA_DECO" else None
        # WHMENU prints engine string 0x2D, "what do you do?", before its
        # labels, so they start 15 columns in. That is why stock Countdown's
        # widest WHMENU is 27 characters where its widest HMENU is 35. Matrix
        # Cubed writes longer labels -- "HELP ROMNEY / CALL SECURITY / AID
        # TERRANS" is 37 -- and the overflow wraps onto the start of the same
        # line, which a play session photographed as "TERRANSMNEY CALL
        # SECURITY AID". Both opcodes end at the same menu routine, so the
        # wide ones become HMENU and lose only the printed prompt.
        shortened = None
        if ins.name in ("SELECT_ACTION", "MENU_HORIZONTAL"):
            labels = [str(a.value) for a in ins.dyn_args if a.type == 0x80]
            if labels:
                budget = WHMENU_BUDGET
                if ins.name == "SELECT_ACTION" and _width(labels) > WHMENU_BUDGET:
                    # Losing the printed prompt buys eight columns.
                    name, budget = "HMENU", HMENU_BUDGET
                    opcode, _ = gen[name]
                elif ins.name == "MENU_HORIZONTAL":
                    budget = HMENU_BUDGET
                if _width(labels) > budget:
                    fitted = fit_labels(labels, budget)
                    if fitted != labels:
                        shortened = dict(zip(labels, fitted))
                        report.append((off, "menu",
                                       f"{_width(labels)} > {budget}: "
                                       f"{labels} -> {fitted}"))
        args = []
        for k, arg in enumerate(list(ins.args) + list(ins.dyn_args)):
            if wall_at == k and arg.type == 0x00:
                new, known = wallmap.translate(arg.value)
                report.append((off, "wall",
                               f"deco {arg.value} -> LOADPIECES {new} "
                               f"(set {new // 3})" + ("" if known else ", unlisted")))
                sel = wallmap.selector(arg.value)
                if sel is not None:
                    wallsel[off] = sel
                args.append(("imm", new))
                continue
            if snd_at == k and arg.type == 0x00:
                new, kind = soundmap.translate(arg.value)
                if kind == "music":
                    report.append((off, "sound",
                                   f"music 0x{arg.value:02X} -> 0x{new:02X} "
                                   f"(slot {soundmap.SLOTS[new]})"))
                elif kind == "effect":
                    report.append((off, "effect",
                                   f"effect {arg.value} -> 0x{new:02X}"))
                args.append(("imm", new))
                continue
            if mon_at == k and arg.type == 0x00 and arg.value == 0xFF \
                    and ins.name == "SPRITE_START":
                # 255 is DOS's "no sprite" sentinel, used 58 times. The
                # Genesis engine loads this operand as a WORD at 0x035A0 and
                # skips on a negative, so a byte 0xFF arrives as 0x00FF --
                # positive -- and the directory search at 0x035A6 has no
                # terminator check. It runs past the table and draws whatever
                # it lands on, which a play session photographed as coloured
                # junk on the floor where a figure belonged.
                #
                # Emitting it as a 16-bit 0xFFFF makes the word negative, so
                # the engine takes the branch it was always meant to.
                report.append((off, "sprite", "SPRITE_START 255 -> 0xFFFF (no sprite)"))
                args.append(("imm", 0xFFFF))
                continue
            if mon_at == k and arg.type == 0x00 and arg.value < 0x80:
                # The two games number monsters independently: Matrix Cubed's
                # 5 and 6 are PURGE COMMANDO and PURGE WARRIOR, Countdown's
                # are HEXADILLO and SAND SQUID. Passing ids through turned
                # the prologue's fight with Terran supremacists into one with
                # poisonous desert wildlife.
                new, exact = monstermap.translate(arg.value)
                if not exact:
                    report.append((off, "monster",
                                   f"{monstermap.DOS_NAMES.get(arg.value, hex(arg.value))}"
                                   f" -> {monstermap.GENESIS.get(new, hex(new))}"))
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
                text = str(arg.value)
                if shortened:
                    text = shortened.get(text, text)
                chunks = _split(text)
                # Only a lone string argument is safe to continue onto a
                # second screen -- an instruction carrying other operands
                # would have them repeated, which is not what any of them
                # mean. In practice the long ones are all PRINT.
                if len(chunks) > 1 and len(ins.args) == 1:
                    overflow = chunks[1:]
                    report.append((off, "text",
                                   f"{len(text)} chars -> {len(chunks)} screens"))
                else:
                    chunks = [text]
                args.append(("str", pool.intern(chunks[0])))
            elif arg.type == 0x81:
                # Still an address, so it goes through the variable map --
                # but it must keep its type. ecl.Argument.is_memory reports
                # True for 0x81, which is how it was being lost.
                args.append(("strptr", map_variable(arg.value, flags, report, off)))
            elif arg.is_memory:
                # Only a jump's operands are code addresses, and not even
                # all of those -- see is_on above. COPY_MEM's first operand
                # is one as well: it names a table inside the block, and it
                # has to move with everything else.
                if (is_jump and not (is_on and k == 0)) or \
                        (ins.name == "COPY_MEM" and k == 0
                         and DOS_BASE <= arg.value < 0xC000):
                    args.append(("code", arg.value))
                else:
                    args.append(("var", map_variable(arg.value, flags, report, off)))
            else:
                args.append(("imm", arg.value))
        # The two engines do not always agree on how many operands an
        # instruction takes, and the interpreter cannot notice. A surplus
        # operand is EXECUTED as the next instruction: DOS LOAD_AREA_DECO
        # carries three where Genesis LOADPIECES takes one, and the first
        # spare byte is 0x00, which is EXIT, so every area's onInit stopped
        # dead at its own wall-set load. A missing operand is as bad the
        # other way -- the interpreter reads the following instruction as
        # the operand, which is what UPDATEFRAME did at the shop door. So
        # the emitted count is made to match the handler.
        want = gen[name][1] if name in gen else None
        if not stub and want is not None and not ins.dyn_args \
                and opcode not in G.DYNAMIC:
            if len(args) > want:
                report.append((off, "arity",
                               f"{ins.name} has {len(args)} operands, {name} takes "
                               f"{want}; the surplus would have been executed"))
                args = args[:want]
            elif len(args) < want:
                report.append((off, "arity",
                               f"{ins.name} has {len(args)} operands, {name} takes "
                               f"{want}; padded, or it would eat what follows"))
                args = args + [("imm", 0)] * (want - len(args))
        if stub:
            # GOTO plus a 3-byte target, and never smaller than what it
            # replaces -- the surplus is skipped over, not executed.
            args = [("skip", 0)]
            size = max(4, ins.size)
        else:
            size = 1 + sum(len(_encode_arg(k, 0 if k in ("code", "var") else v))
                           for k, v in args)
        layout[off] = redraw_pos.get(off, pos)
        pieces.append((off, opcode, args, size))
        pos += size
        # Continued screens follow, each behind a wait so the player reads
        # one before the next replaces it. `layout[off]` already points at
        # the first piece, so every jump to this instruction still lands on
        # the start of the sequence.
        for chunk in overflow:
            cont, _ = gen["CONTINUE"]
            pieces.append((off, cont, [], 1))
            pos += 1
            more = [("str", pool.intern(chunk))]
            msize = 1 + sum(len(_encode_arg(k, v)) for k, v in more)
            pieces.append((off, opcode, more, msize))
            pos += msize
        if off in wallsel:
            # LOADPIECES loads the graphics; this is what makes the engine
            # load the piece TABLES, without which 0x97AD is never computed.
            view, _ = gen["VIEW"]
            varg = [("imm", 4), ("imm", wallsel[off])]
            vsize = 1 + sum(len(_encode_arg(k, v)) for k, v in varg)
            pieces.append((off, view, varg, vsize))
            pos += vsize
            report.append((off, "wall", f"VIEW 4,0x{wallsel[off]:02X} after "
                                        f"LOADPIECES, to load the piece tables"))
        if off in restore_after:
            view, _ = gen["VIEW"]
            varg = [("imm", 0), ("imm", 0xFF)]
            vsize = 1 + sum(len(_encode_arg(k, v)) for k, v in varg)
            pieces.append((off, view, varg, vsize))
            pos += vsize
            report.append((off, "combat", "VIEW 0,255 after COMBAT, which "
                                          "leaves the display disabled"))

    # Pass 2: emit, rebasing jump targets through the new layout.
    out = bytearray()
    for off, opcode, args, size in pieces:
        here = len(out)
        if opcode is None:                 # a verbatim data table
            out += args
            continue
        out.append(opcode)
        for kind, value in args:
            if kind == "skip":
                # Step over this instruction to the next one. The slot may be
                # wider than the GOTO needs, and the surplus is skipped, not
                # executed, so it is simply padded out.
                out += _encode_arg("skip", here + size + GEN_BASE)
                continue
            if kind == "code":
                target = value - DOS_BASE + marker
                if target in layout:
                    value = layout[target] + GEN_BASE
                else:
                    report.append((off, "jump", f"target 0x{value:04X} not in layout"))
                    value = GEN_BASE
            out += _encode_arg(kind, value)
        if len(out) - here < size:
            out += bytes(size - (len(out) - here))
    return bytes(out), pool.build(), report

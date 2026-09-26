"""
Translate Matrix Cubed's NPC ids into Countdown's ADDNPC table.

`ADDNPC` (opcode 0x36) takes an id and a percentage. The handler at `0x0488C`
finds the first empty slot in the eight-entry party array at `0xFFC470`, then
scans a table of byte PAIRS at `0x048DA` for the id and calls `0x048E8`:

    048B8: lea.l   $48da.l, a0
    048BE: cmp.b   (a0)+, d2
    048C0: beq.b   $48c6
    048C2: addq.l  #$1, a0
    048C4: bra.b   $48be

**That loop has no terminator.** The table is seven pairs and ends at
`0x048E8`, which is the loader's own first instruction, so an id that is not
in the table scans on into 68000 code until some byte happens to equal it and
then takes the byte after as a character record. There is no miss path and no
error message.

**The id is the roster record id.** The second byte of each pair goes into
`d4`, which `0x048E8` never reads -- the roster search at `0x04928` compares
`d2`, the id itself. Countdown's own table confirms it: `0x3B 0x3C 0x3D 0x3E`
are TUSKON, LEANDER, ZANE and BUCK ROGERS, and `0x6A 0x6B 0x6C` are BEOWULF
SAND, JASON BRAGA and CARLOS RIOJA -- all roster records by those very
numbers. (The first reading of this file had the second byte as the record
id, which put RAM WARRIOR in the party instead of Killer Kane; a play session
caught it as "there was no Kane".) So the table only says which ids are
allowed to join, and a map has to name the ROSTER id.

Countdown's table holds `0x3B 0x3C 0x3D 0x3E 0x6A 0x6B 0x6C`; Matrix Cubed's scripts ask for `0x1E`, `0x37` and `0x39` at eight
sites across blocks 1, 24, 50 and 80. The intersection is empty, so **every**
`ADDNPC` in the port was running off the end of that table.

The symptom a play session saw was the attract demo's fight arriving with one
combatant instead of four. Block 1 is worse and quieter: it is the opening
dock, where `NPC_ADD 0x39` is Buck Rogers joining the party.

The mapping is easy, because Matrix Cubed is the sequel and the cast carries
over -- Countdown's own table already has both characters by name:

    Matrix Cubed 0x37  LEANDER      -> Countdown 0x3C  LEANDER
    Matrix Cubed 0x39  BUCK ROGERS  -> Countdown 0x3E  BUCK ROGERS

`0x1E` is KILLER KANE, who is not in Countdown at all. He does NOT get
substituted: `add_creatures.py` already puts him in the roster at `0x42`
with 90 hit points and his own figure, so he maps there like the others and
`npctable.py` adds `0x42` to the table so the scan will accept it.
Substituting was tried first and sent him to ZANE, who has **4 hit points**
-- a play session spotted that immediately as "a baby on my team".
"""

# Countdown's table, for reading the map below: npc id -> name.
GENESIS = {
    0x3B: "TUSKON", 0x3C: "LEANDER", 0x3D: "ZANE", 0x3E: "BUCK ROGERS",
    # These three point at roster records 0x8A, 0x83 and 0x87, which are past
    # the named part of the monster roster and have not been identified.
    0x6A: "BEOWULF SAND", 0x6B: "JASON BRAGA", 0x6C: "CARLOS RIOJA",
    0x42: "KILLER KANE",    # added to the table by npctable.py
}

DOS_NAMES = {0x1E: "KILLER KANE", 0x37: "LEANDER", 0x39: "BUCK ROGERS"}

# Matrix Cubed id -> Countdown id, and whether the character is the same one.
MAP = {
    0x37: (0x3C, True),     # LEANDER     -> LEANDER, the same character
    0x39: (0x3E, True),     # BUCK ROGERS -> BUCK ROGERS, the same character
    0x1E: (0x42, True),     # KILLER KANE -> KILLER KANE, added to the roster
}

# Roster ids npctable.py ADDS to the table, so the scan will accept them.
# The second byte mirrors the id, which is what Countdown does for its own
# four; `d4` is not read by the loader either way.
ADDED = {0x42: 0x42}        # KILLER KANE

# Where an id is already one of Countdown's, leave it alone.
NATIVE = set(GENESIS) | set(ADDED)


def translate(npc_id):
    """(Countdown npc id, whether it is the same character)."""
    if npc_id in MAP:
        return MAP[npc_id]
    if npc_id in NATIVE:
        return npc_id, True
    # Not in either table. Anything emitted here would send the unterminated
    # scan into code, so fall back to a real entry rather than pass it
    # through: a wrong NPC is recoverable and a wild record is not.
    return 0x3E, False


if __name__ == "__main__":
    for dos in sorted(set(MAP) | NATIVE):
        gid, exact = translate(dos)
        print("  0x%02X %-12s -> 0x%02X %-12s %s"
              % (dos, DOS_NAMES.get(dos, GENESIS.get(dos, "?")), gid,
                 GENESIS.get(gid, "?"), "" if exact else "(nearest fit)"))

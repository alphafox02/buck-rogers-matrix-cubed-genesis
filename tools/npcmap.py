"""
Translate Matrix Cubed's NPC ids into Countdown's ADDNPC table.

`ADDNPC` (opcode 0x36) takes a roster id and a percentage. The handler at
`0x0488C` finds the first empty slot in the eight-entry party array at
`0xFFC470`, then looks the id up in a table of `(npc id, record id)` pairs at
`0x048DA` and loads that record through `0x048E8`:

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

And nothing lined up. Countdown's table holds `0x3B 0x3C 0x3D 0x3E 0x6A 0x6B
0x6C`; Matrix Cubed's scripts ask for `0x1E`, `0x37` and `0x39` at eight
sites across blocks 1, 24, 50 and 80. The intersection is empty, so **every**
`ADDNPC` in the port was running off the end of that table.

The symptom a play session saw was the attract demo's fight arriving with one
combatant instead of four. Block 1 is worse and quieter: it is the opening
dock, where `NPC_ADD 0x39` is Buck Rogers joining the party.

The mapping is easy, because Matrix Cubed is the sequel and the cast carries
over -- Countdown's own table already has both characters by name:

    Matrix Cubed 0x37  LEANDER      -> Countdown 0x3C  LEANDER
    Matrix Cubed 0x39  BUCK ROGERS  -> Countdown 0x3E  BUCK ROGERS

`0x1E` is KILLER KANE, who has no counterpart -- he is Matrix Cubed's
villain and Countdown never carried him as a joinable NPC. He goes to ZANE
(`0x3D`), on the same "nearest equivalent in role" principle monstermap.py
uses: a named human of fighting weight rather than a wrong-sized substitute.
"""

# Countdown's table, for reading the map below: npc id -> name.
GENESIS = {
    0x3B: "TUSKON", 0x3C: "LEANDER", 0x3D: "ZANE", 0x3E: "BUCK ROGERS",
    # These three point at roster records 0x8A, 0x83 and 0x87, which are past
    # the named part of the monster roster and have not been identified.
    0x6A: "(record 0x8A)", 0x6B: "(record 0x83)", 0x6C: "(record 0x87)",
}

DOS_NAMES = {0x1E: "KILLER KANE", 0x37: "LEANDER", 0x39: "BUCK ROGERS"}

# Matrix Cubed id -> Countdown id, and whether the character is the same one.
MAP = {
    0x37: (0x3C, True),     # LEANDER     -> LEANDER
    0x39: (0x3E, True),     # BUCK ROGERS -> BUCK ROGERS
    0x1E: (0x3D, False),    # KILLER KANE -> ZANE, nearest in role
}

# Where an id is already one of Countdown's, leave it alone.
NATIVE = set(GENESIS)


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

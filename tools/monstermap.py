"""
Translate Matrix Cubed monster ids into Countdown's roster.

The two games number monsters independently, exactly as they number skills
independently. Matrix Cubed's id 5 is a PURGE COMMANDO and its 6 a PURGE
WARRIOR; Countdown's 5 is a HEXADILLO and its 6 a SAND SQUID. Passing the
ids through unchanged turns the Salvation prologue's fight with Terran
supremacists into a fight with poisonous desert wildlife, which is what a
play session reported: "I'm fighting squids and they've poisoned half my
team... seems odd for a beginning."

Rosters:

  DOS      63 records in `dos_game/matrix/MON0CHA.DAX`, name at the start
           of each block.
  Genesis  54 records in a stream at 0x9E77C, laid out like the GEO stream
           -- a count word, then that many ids, then fixed 214-byte records
           with the name first. The loader at 0x048E8 searches the id list
           and prints "couldnt load monster" on a miss. Its id buffer is
           0x40 bytes, so the engine caps at 64 monsters.

Where a creature exists in both, it maps by name. Where it does not, it
maps to the nearest equivalent in role -- a leader to a leader, a security
robot to a security robot, an insect to an insect -- because substituting a
creature of the wrong weight is what made the opening fight unwinnable.
"""

# Genesis id -> name, for reading the table below.
GENESIS = {
    0x00: "D.R. WARRIOR",    0x01: "LL. WARRIOR",     0x02: "LL. TECHNICIAN",
    0x04: "DESERT APE",      0x05: "HEXADILLO",       0x06: "SAND SQUID",
    0x07: "MER. LEADER",     0x08: "MER. TECHNICIAN", 0x09: "MER. H.S. ROBOT",
    0x0A: "SM. E.C. GENNIE", 0x0B: "LG. E.C. GENNIE", 0x0C: "PIRATE WARRIOR",
    0x0D: "PIRATE LEADER",   0x0E: "P. COMBAT ROBOT", 0x0F: "RAM ASSASSIN",
    0x10: "RAM G.D. GENNIE", 0x11: "HYPERCRAB",       0x12: "HYPERSCORP",
    0x13: "HYPERSNAKE",      0x14: "RAM MAR CGENNIE", 0x17: "RAM ASSAULT BOT",
    0x18: "RAM COMBAT BOT",  0x1A: "RAM H.D. ROBOT",  0x1C: "RAM H.S. ROBOT",
    0x1D: "RAM TECHNICIAN",  0x1E: "RAM WARRIOR",     0x1F: "SPACE RAT",
    0x20: "TERRINE LEADER",  0x21: "SWAMP HORNET",    0x22: "URSADDER",
    0x23: "ACID FROG",       0x24: "ACIDICIUM",       0x26: "MER. WARRIOR",
    0x27: "NEO WARRIOR",     0x29: "TERRINE WARRIOR", 0x2A: "STAGE 3  ECG",
    0x3A: "TALON",           0x3B: "TUSKON",          0x3C: "LEANDER",
    0x3D: "ZANE",            0x3E: "BUCK ROGERS",
}

# DOS id -> (Genesis id, exact name match?)
MAP = {
    0x01: (0x01, False),  # SID REFUGE      -> LL. WARRIOR
    0x02: (0x01, False),
    0x03: (0x01, False),
    0x04: (0x01, False),
    0x05: (0x20, False),  # PURGE COMMANDO  -> TERRINE LEADER (Terran supremacists)
    0x06: (0x29, False),  # PURGE WARRIOR   -> TERRINE WARRIOR
    0x07: (0x27, False),  # WARRIOR         -> NEO WARRIOR
    0x08: (0x1C, False),  # PURGE SEC ROBOT -> RAM H.S. ROBOT
    0x09: (0x12, False),  # ORG SKORP       -> HYPERSCORP
    0x0A: (0x04, False),  # COYODORG        -> DESERT APE
    0x0B: (0x1F, False),  # RATWURST        -> SPACE RAT
    0x0C: (0x0D, False),  # GANG LEADER     -> PIRATE LEADER
    0x0D: (0x0C, False),  # GANG VETERAN    -> PIRATE WARRIOR
    0x0E: (0x01, False),  # LUNARIAN WARR   -> LL. WARRIOR
    0x0F: (0x01, False),
    0x10: (0x20, False),  # LUNARIAN LEADER -> TERRINE LEADER
    0x11: (0x1C, False),  # LUNAR SEC ROBOT -> RAM H.S. ROBOT
    0x12: (0x21, False),  # CARNIFERN       -> SWAMP HORNET
    0x13: (0x26, False),  # AMALTHEAN WARR  -> MER. WARRIOR
    0x14: (0x07, False),  # AMALTHEAN LEAD  -> MER. LEADER
    0x15: (0x09, False),  # AMALTH SEC BOT  -> MER. H.S. ROBOT
    0x16: (0x24, False),  # VENUS DINOSAUR  -> ACIDICIUM
    0x17: (0x02, False),  # LOWLANDER MINER -> LL. TECHNICIAN
    0x18: (0x29, True),   # TERRINE WARRIOR
    0x19: (0x01, False),  # LOWLANDER       -> LL. WARRIOR
    0x1A: (0x00, False),  # DESERT RUNNER   -> D.R. WARRIOR
    0x1B: (0x01, False),
    0x1C: (0x00, False),
    0x1D: (0x27, False),  # STORMRIDER      -> NEO WARRIOR
    0x1E: (0x3A, False),  # KILLER KANE     -> TALON  (named villain)
    0x1F: (0x3B, False),  # DR. J. MALCOLN  -> TUSKON (named)
    0x20: (0x2A, False),  # STAGE 5 ECG     -> STAGE 3 ECG
    0x21: (0x26, True),   # MER. WARRIOR
    0x23: (0x09, True),   # MER. H.S. ROBOT
    0x24: (0x11, True),   # HYPERCRAB
    0x25: (0x13, True),   # HYPERSNAKE
    0x26: (0x1D, False),  # TECHNICIAN      -> RAM TECHNICIAN
    0x27: (0x0B, True),   # LG. E.C. GENNIE
    0x28: (0x06, True),   # SAND SQUID
    0x29: (0x22, True),   # URSADDER
    0x2A: (0x23, True),   # ACID FROG
    0x2B: (0x0C, True),   # PIRATE WARRIOR
    0x2C: (0x0D, True),   # PIRATE LEADER
    0x2D: (0x0E, False),  # PIR. COM. ROBOT -> P. COMBAT ROBOT
    0x2E: (0x0F, True),   # RAM ASSASSIN
    0x2F: (0x10, True),   # RAM G.D. GENNIE
    0x30: (0x17, False),  # ASSAULT ROBOT   -> RAM ASSAULT BOT
    0x31: (0x18, False),  # COMBAT ROBOT    -> RAM COMBAT BOT
    0x32: (0x1C, False),  # SECURITY ROBOT  -> RAM H.S. ROBOT
    0x33: (0x1A, False),  # DEFENSE ROBOT   -> RAM H.D. ROBOT
    0x34: (0x1E, True),   # RAM WARRIOR
    0x35: (0x1D, False),  # TECHNICIAN      -> RAM TECHNICIAN
    0x36: (0x14, False),  # RAM CBT. GENNIE -> RAM MAR CGENNIE
    0x37: (0x3C, True),   # LEANDER
    0x38: (0x3D, True),   # ZANE
    0x39: (0x3E, True),   # BUCK ROGERS
    0x3A: (0x0C, False),  # GANG MEMBER     -> PIRATE WARRIOR
    0x3B: (0x0C, False),  # GANG RECRUIT    -> PIRATE WARRIOR
    0x3C: (0x00, True),   # D.R. WARRIOR
    0x3D: (0x01, True),   # LL. WARRIOR
    0x3E: (0x01, True),   # LL. WARRIOR
    0x3F: (0x24, False),  # JOVIAN DRAGON   -> ACIDICIUM
    0x40: (0x21, False),  # WASPHOPPER      -> SWAMP HORNET
}

DOS_NAMES = {
    0x01: "SID REFUGE", 0x05: "PURGE COMMANDO", 0x06: "PURGE WARRIOR",
    0x07: "WARRIOR", 0x08: "PURGE SEC ROBOT", 0x09: "ORG SKORP",
    0x0A: "COYODORG", 0x0B: "RATWURST", 0x0C: "GANG LEADER",
    0x0D: "GANG VETERAN", 0x0E: "LUNARIAN WARR", 0x10: "LUNARIAN LEADER",
    0x11: "LUNAR SEC ROBOT", 0x12: "CARNIFERN", 0x13: "AMALTHEAN WARR",
    0x14: "AMALTHEAN LEAD", 0x15: "AMALTH SEC BOT", 0x16: "VENUS DINOSAUR",
    0x17: "LOWLANDER MINER", 0x18: "TERRINE WARRIOR", 0x19: "LOWLANDER",
    0x1A: "DESERT RUNNER", 0x1D: "STORMRIDER", 0x1E: "KILLER KANE",
    0x1F: "DR. J. MALCOLN", 0x20: "STAGE 5 ECG", 0x21: "MER. WARRIOR",
    0x23: "MER. H.S. ROBOT", 0x24: "HYPERCRAB", 0x25: "HYPERSNAKE",
    0x26: "TECHNICIAN", 0x27: "LG. E.C. GENNIE", 0x28: "SAND SQUID",
    0x29: "URSADDER", 0x2A: "ACID FROG", 0x2B: "PIRATE WARRIOR",
    0x2C: "PIRATE LEADER", 0x2D: "PIR. COM. ROBOT", 0x2E: "RAM ASSASSIN",
    0x2F: "RAM G.D. GENNIE", 0x30: "ASSAULT ROBOT", 0x31: "COMBAT ROBOT",
    0x32: "SECURITY ROBOT", 0x33: "DEFENSE ROBOT", 0x34: "RAM WARRIOR",
    0x35: "TECHNICIAN", 0x36: "RAM CBT. GENNIE", 0x37: "LEANDER",
    0x38: "ZANE", 0x39: "BUCK ROGERS", 0x3A: "GANG MEMBER",
    0x3B: "GANG RECRUIT", 0x3C: "D.R. WARRIOR", 0x3D: "LL. WARRIOR",
    0x3F: "JOVIAN DRAGON", 0x40: "WASPHOPPER",
}

FALLBACK = 0x27          # NEO WARRIOR -- a plain humanoid


def translate(dos_id):
    """Return (genesis_id, exact) for a DOS monster id."""
    if dos_id in MAP:
        return MAP[dos_id]
    return FALLBACK, False

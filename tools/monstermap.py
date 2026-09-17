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
    """
    Return (genesis_id, exact) for a DOS monster id.

    A creature with a slot of its own goes there and counts as exact: it
    carries Matrix Cubed's name and its role match's stats. Everything else
    falls back on substitution, which is where this file started.
    """
    new = DOS_TO_NEW.get(dos_id)
    if new is not None:
        return new, True
    if dos_id in MAP:
        return MAP[dos_id]
    return FALLBACK, False


# Creatures Matrix Cubed has and Countdown never did.
#
# Substituting by role keeps a fight the right shape, but the player reads
# the substitute's name -- Purge commandos announcing themselves as Terrine
# leaders. These get slots of their own instead.
#
# A new slot clones the record of the creature it used to stand in for, so
# it inherits stats that suit the role, and takes Matrix Cubed's name. The
# 214-byte record layout has not been reversed and does not need to be: a
# clone is a valid record by construction.
#
# Monster id and figure id are the same number, so each also needs a figure
# record at the same id -- tools/expand_figures.py adds one cloning the same
# source, which is why the creature looks like what it replaced until its
# own artwork is converted.
#
# Names are deduplicated. Matrix Cubed lists SID REFUGE four times at
# different power levels, and those share one slot.
#
#   new id: (name, the Genesis monster it clones)
NEW_CREATURES = {
    0x2E: ("AMALTH SEC BOT", 0x09),            # DOS [21]
    0x2F: ("AMALTHEAN LEAD", 0x07),            # DOS [20]
    0x30: ("AMALTHEAN WARR", 0x26),            # DOS [19]
    0x31: ("ASSAULT ROBOT", 0x17),             # DOS [48]
    0x32: ("CARNIFERN", 0x21),                 # DOS [18]
    0x33: ("COMBAT ROBOT", 0x18),              # DOS [49]
    0x34: ("COYODORG", 0x04),                  # DOS [10]
    0x35: ("DEFENSE ROBOT", 0x1A),             # DOS [51]
    0x36: ("DESERT RUNNER", 0x00),             # DOS [26, 28]
    0x37: ("DR. J. MALCOLN", 0x3B),            # DOS [31]
    0x38: ("GANG LEADER", 0x0D),               # DOS [12]
    0x39: ("GANG MEMBER", 0x0C),               # DOS [58]
    0x3F: ("GANG RECRUIT", 0x0C),              # DOS [59]
    0x40: ("GANG VETERAN", 0x0C),              # DOS [13]
    0x41: ("JOVIAN DRAGON", 0x24),             # DOS [63]
    0x42: ("KILLER KANE", 0x3A),               # DOS [30]
    0x43: ("LOWLANDER", 0x01),                 # DOS [25, 27]
    0x44: ("LOWLANDER MINER", 0x02),           # DOS [23]
    0x45: ("LUNAR SEC ROBOT", 0x1C),           # DOS [17]
    0x46: ("LUNARIAN LEADER", 0x20),           # DOS [16]
    0x47: ("LUNARIAN WARR", 0x01),             # DOS [14, 15]
    0x48: ("ORG SKORP", 0x12),                 # DOS [9]
    0x49: ("PIR. COM. ROBOT", 0x0E),           # DOS [45]
    0x4A: ("PURGE COMMANDO", 0x20),            # DOS [5]
    0x4B: ("PURGE SEC ROBOT", 0x1C),           # DOS [8]
    0x4C: ("PURGE WARRIOR", 0x29),             # DOS [6]
    0x4D: ("RAM CBT. GENNIE", 0x14),           # DOS [54]
    0x4E: ("RATWURST", 0x1F),                  # DOS [11]
    0x4F: ("SECURITY ROBOT", 0x1C),            # DOS [50]
    0x50: ("SID REFUGE", 0x01),                # DOS [1, 2, 3, 4]
    0x51: ("STAGE 5 ECG", 0x2A),               # DOS [32]
    0x52: ("STORMRIDER", 0x27),                # DOS [29]
    0x53: ("TECHNICIAN", 0x1D),                # DOS [38, 53]
    0x54: ("VENUS DINOSAUR", 0x24),            # DOS [22]
    0x55: ("WARRIOR", 0x27),                   # DOS [7]
    0x56: ("WASPHOPPER", 0x21),                # DOS [64]
}

# DOS monster id -> the new slot, for the ids these creatures cover.
DOS_TO_NEW = {}
for _nid, (_name, _src) in NEW_CREATURES.items():
    for _did, _n in DOS_NAMES.items():
        if _n == _name:
            DOS_TO_NEW[_did] = _nid

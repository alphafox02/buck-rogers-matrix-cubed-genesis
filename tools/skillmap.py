# SPDX-License-Identifier: MIT
"""
Translate DOS Buck Rogers skill ids into the Genesis engine's 19.

DOS uses the full tabletop skill list -- 84 skills grouped by attribute,
named in a table at 0x0F336 of START.EXE. ECL refers to them 1-based, which
the landing check in block 19 pins down: it asks for skill 51, and table
index 50 is `Pilot Rocket`.

The Genesis port condensed all of that into 19 skills, printed from the
engine string table as index 0x54 + id:

    04EE4: moveq   #$54, d0
    04EE6: add.w   d7, d0
    04EE8: jsr     $11c8e

So passing a DOS id straight through indexes far past the skill names and
into unrelated engine text -- DOS 46 (Astrogation) printed `career and`,
which is what a play session actually showed.

Where a DOS skill has no Genesis counterpart it maps to the nearest one the
engine can roll. Exact matches are marked; the rest are judgement calls and
are listed in docs/compatibility.md so they can be argued with.
"""

# The Genesis engine's skills, string 0x54 + index.
GENESIS = [
    "pilot rocket/juryrig", "treat wounds", "tactics/leadership",
    "bypass security", "zero gravity maneuvering", "perception",
    "demolition", "stealth", "climbing", "fast talk", "first aid",
    "repair rocket", "library search", "programming", "mono sword",
    "needle gun", "heat gun", "laser pistol", "rocket pistol",
]

PILOT, TREAT, TACTICS, BYPASS, ZEROG, PERCEPTION, DEMO, STEALTH, \
    CLIMB, FASTTALK, FIRSTAID, REPAIR, LIBRARY, PROGRAM = range(14)

# DOS ECL id (1-based) -> Genesis skill index. `True` marks an exact match
# of meaning rather than a nearest-fit.
MAP = {
     1: (REPAIR,    False),  # Repair Electrical
     6: (PILOT,     True),   # Jury Rig -- the Genesis skill is literally
                             # "pilot rocket/juryrig"
     7: (BYPASS,    True),   # Bypass Security
     8: (BYPASS,    False),  # Open Lock
     9: (PROGRAM,   False),  # Commo Operation
    10: (PERCEPTION,False),  # Sensor Operation
    11: (DEMO,      True),   # Demolitions
    13: (FIRSTAID,  True),   # First Aid
    14: (REPAIR,    False),  # Repair Weapon
    16: (TREAT,     False),  # Life Suspension Tech
    18: (TREAT,     True),   # Treat Serious Wounds
    21: (TREAT,     False),  # Treat Stun/Paralysis
    23: (TREAT,     False),  # Diagnose
    43: (PROGRAM,   True),   # Programming
    45: (LIBRARY,   True),   # Library Search
    46: (PILOT,     False),  # Astrogation
    50: (FASTTALK,  False),  # Disguise
    51: (PILOT,     True),   # Pilot Rocket
    61: (STEALTH,   True),   # Hide in Shadows
    62: (STEALTH,   True),   # Move Silently
    64: (CLIMB,     False),  # Acrobatics
    65: (CLIMB,     True),   # Climb
    69: (FASTTALK,  False),  # Paint/Draw
    70: (FASTTALK,  False),  # Hypnosis
    72: (FASTTALK,  False),  # Intimidate
    74: (FASTTALK,  False),  # Befriend Animal
    76: (FASTTALK,  True),   # Fast Talk/Convince
    78: (FASTTALK,  False),  # Distract
    79: (FASTTALK,  False),  # Etiquette
    81: (STEALTH,   False),  # Shadowing
    83: (PERCEPTION,True),   # Notice
    84: (PERCEPTION,False),  # Planetary Survival
}

# Read out of START.EXE at 0x0F336; 1-based, so DOS_NAMES[id] is direct.
DOS_NAMES = {
     1: "Repair Electrical",   6: "Jury Rig",          7: "Bypass Security",
     8: "Open Lock",           9: "Commo Operation",  10: "Sensor Operation",
    11: "Demolitions",        13: "First Aid",        14: "Repair Weapon",
    16: "Life Suspension Tech", 18: "Treat Serious Wounds",
    21: "Treat Stun/Paralysis", 23: "Diagnose",       43: "Programming",
    45: "Library Search",     46: "Astrogation",      50: "Disguise",
    51: "Pilot Rocket",       61: "Hide in Shadows",  62: "Move Silently",
    64: "Acrobatics",         65: "Climb",            69: "Paint/Draw",
    70: "Hypnosis",           72: "Intimidate",       74: "Befriend Animal",
    76: "Fast Talk/Convince", 78: "Distract",         79: "Etiquette",
    81: "Shadowing",          83: "Notice",           84: "Planetary Survival",
}

FALLBACK = PERCEPTION


def translate(dos_id):
    """Return (genesis_id, exact) for a DOS ECL skill id."""
    if dos_id in MAP:
        return MAP[dos_id]
    return FALLBACK, False

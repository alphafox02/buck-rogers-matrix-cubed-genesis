# SPDX-License-Identifier: MIT
"""
Allocate Matrix Cubed's script-only flags into Genesis RAM.

Of the 418 addresses Matrix Cubed's scripts touch, 368 are story flags --
quest state, doors opened, NPCs spoken to -- written and read only by ECL.
Their numeric addresses mean nothing to the engine, so they do not need
matching counterparts; they need somewhere safe to live.

They cannot simply be passed through. DOS puts them at 0x0101-0xC01E, and
Genesis ECL addresses are used as 68000 absolute-short operands, which
sign-extend: anything below 0x8000 resolves into ROM. A DOS flag at 0x4C54
would become 0x00004C54 and the write would go nowhere.

Two sources of space, preferred in order:

 1. **The flags Countdown itself uses.** We are replacing its campaign, so
    its story flags are free, and they are provably safe RAM because the
    shipped game keeps its own flags there. 193 addresses.

 2. **Gaps within the same region.** Addresses in 0x9000-0x9FFF touched by
    neither Countdown's scripts nor its engine code. The engine's memory map
    evidently assigns that range to script state, so a gap inside it is far
    safer than free-looking RAM elsewhere: detection of engine use relies on
    absolute-short operands and cannot see access through a register, so
    distance from known-used addresses is not evidence of safety.

Both per-character windows (0x9AFC-0x9B4F and 0x9BF6-0x9C0F) are excluded --
the address resolver at 0x042E0 redirects those into character records, so a
flag placed there would be silently scattered across the party.
"""

import collections
import re
import struct
from pathlib import Path

import dax
import ecl
import genesis_disasm as G
import genesis_ecl

REPO = Path(__file__).resolve().parent.parent

WINDOWS = set(range(0x9AFC, 0x9B50)) | set(range(0x9BF6, 0x9C10))

# RAM the engine wipes on every area change, found by disassembling its clear
# loops. A story flag placed here would reset whenever the player walked
# between areas, so quest state would never persist -- and the failure would
# look like bad script logic rather than bad allocation.
#
#   0385A  lea.l $97F6.w,a0 / moveq #7,d0 / move.l d1,(a0)+ / dbra
#   03868  lea.l $9E6F.w,a0 / moveq #9,d0 / move.b d1,(a0)+ / dbra
#
# Countdown uses addresses in the first range itself, which is precisely why
# reusing its script variables wholesale was unsafe: some of them are
# deliberately volatile per-area scratch, not campaign flags.
#
# The much larger clear at 0x0115A covers 0x96F6-0x9EF5 but runs once at
# start-up, so it is harmless -- flags should begin at zero anyway.
VOLATILE = set(range(0x97F6, 0x9816)) | set(range(0x9E6F, 0x9E79))
# The region is 0x96F6-0x9EF5, not 0x9000-0x9FFF. Both ends matter.
#
# Below 0x96F6 is the buffer the ECL loader decompresses a script into --
# the bounds the interpreter itself checks at 0x03308 -- so a flag there is
# a byte of the running script. Work RAM after boot shows it plainly: 0x9000
# onward reads 87, 73, 73, 71, 78, 84, ... the ASCII of the block's own text.
#
# Above 0x9EF5 is past the engine's start-up clear at 0x0115A, so it holds
# whatever the machine powered on with. Reading the region at the main menu,
# before any script has run, finds 266 non-zero bytes in 0x9EF6-0x9FFF and
# none at all between 0x9B9F and 0x9EF5.
#
# A flag that does not start at zero is worse than a flag that does not
# persist: every story guard in a Gold Box script is "if this is not zero,
# I have already happened". The Romney encounter on the opening dock reads
# `COMPARE [flag], 0 / IF_NOT_EQUALS / EXIT`, its flag landed on 0x991A,
# and 0x991A is 2 before the title screen -- so the scene silently never
# fired.
REGION = range(0x96F6, 0x9EF6)

# Addresses inside the region that are STILL not zero at the main menu, with
# no script yet run. Measured, not reasoned about: boot the build, stop at
# the menu, and read 0x96F6-0x9EF5 out of the savestate. Most are engine
# state the start-up clear runs before rather than after.
#
# To re-measure after an engine change, dump work RAM at the menu and list
# every non-zero byte in the region; anything new belongs here.
NOT_ZEROED = (
    {0x97F2, 0x9AFB} |
    set(range(0x98F6, 0x9923)) |      # 0x98F6-0x9922, in six broken runs
    set(range(0x9BBD, 0x9BBF)) |
    set(range(0x9BC7, 0x9BCB)) |
    set(range(0x9BD2, 0x9BD5))
)

# Engine-shared Genesis addresses established so far; never reassign these.
CONFIRMED = {0x9E6F, 0x9E70, 0x9E71, 0x97E8, 0x9AFA, 0x9AF6, 0x9AF7}

# DOS addresses that are engine-shared but NOT named in the configuration,
# because they are continuations of a named one. The config names
# TEMP_START at 0x7F79 and says nothing about the scratch slots that follow,
# but 0x7F7A and 0x7F7B are the same bank -- they correspond to Genesis
# 0x9E70 and 0x9E71, which is how the scratch mapping was confirmed. Treating
# them as free story flags would reassign live scratch registers.
DOS_ENGINE_EXTRA = (
    set(range(0x7F79, 0x7F80)) |      # scratch bank
    set(range(0x7C00, 0x7C50)) |      # selected-character record
    set(range(0x7D00, 0x7D1A)) |      # selected-character status
    set(range(0xC04B, 0xC050))        # dungeon position and current square
)


# The engine's own code, for the scan below. 0x200 is past the vector table
# and the header; everything above 0x20000 is compressed resources.
CODE = (0x200, 0x20000)


def engine_addresses(rom: bytes):
    """Every address in the region the engine's own 68000 code names.

    Countdown's scripts and its engine share this region, so "an address
    Countdown's scripts use" is NOT the same as "an address free for a story
    flag". 0x97DC is both: scripts write it, and the engine reads it at
    0x082C6 to choose which screen layout to draw, while the VIEW handler
    writes 0xA8 or 0xA2 into it at 0x03DFA. Handed out as a flag it became
    Matrix Cubed's hotel day counter, so leaving the Rising Sun incremented
    the layout selector and the view came back as garbage tiles under a
    spaceship control panel.

    This reads every aligned word of the engine's code and takes any value
    in the region as spoken for. That over-counts -- a constant or a piece
    of table data in the same numeric range is not an address -- but the
    pool has 3,587 slots for 385 flags, so being wrong in this direction
    costs nothing and being wrong in the other corrupts live engine state.
    """
    lo, hi = CODE
    return {v for v in (struct.unpack_from(">H", rom, pos)[0]
                        for pos in range(lo, hi, 2))
            if v in REGION}


def mapped_targets():
    """Genesis addresses the transpiler already assigns by name."""
    import transpile
    out = set(transpile.VARIABLE_MAP.values()) | set(transpile.PROBABLE_MAP.values())
    for lo, hi, base in transpile.WINDOW_MAP:
        out.update(range(base, base + (hi - lo)))
    return out


def countdown_flags(rom: bytes):
    """Addresses Countdown's own scripts use, which its campaign no longer needs."""
    table = G.load_opcodes()
    seen = collections.Counter()
    for _bid, code, _text in genesis_ecl.directory(rom):
        for ins in G.disassemble(genesis_ecl.decompress(code), table).values():
            if ins.name in {"GOTO", "GOSUB", "ONGOTO", "ONGOSUB"}:
                continue
            for a in ins.args:
                if a.kind == "mem" and a.value in REGION:
                    seen[a.value] += 1
    return sorted(a for a in seen
                  if a not in CONFIRMED and a not in WINDOWS
                  and a not in VOLATILE and a not in NOT_ZEROED)


def region_gaps(rom: bytes, engine_used):
    """Unused addresses inside the region the engine devotes to script state."""
    table = G.load_opcodes()
    script = set()
    for _bid, code, _text in genesis_ecl.directory(rom):
        for ins in G.disassemble(genesis_ecl.decompress(code), table).values():
            for a in ins.args:
                if a.kind == "mem":
                    script.add(a.value)
    taken = script | set(engine_used) | WINDOWS | CONFIRMED | VOLATILE | NOT_ZEROED
    return [a for a in REGION if a not in taken]


def matrix_flags(path=None):
    """Script-only addresses Matrix Cubed uses, ordered by how often."""
    cfg = Path("/tmp/ssi/src/main/resources/Buck Rogers - Matrix Cubed.properties")
    named = set()
    if cfg.exists():
        named = {int(m.group(1), 16)
                 for m in re.finditer(r"address\.\w+=([0-9A-Fa-f]+)", cfg.read_text())}
    counts = collections.Counter()
    for _bid, block in dax.load(path or REPO / "dos_game/matrix/ECL1.DAX").items():
        found, _e, _err = ecl.disassemble_block(block)
        for ins in found.values():
            if ins.name in {"GOTO", "GOSUB", "ON_GOTO", "ON_GOSUB"}:
                continue
            for a in ins.args:
                if a.is_memory:
                    counts[a.value] += 1
    # Engine-config addresses the Genesis has no counterpart for are given
    # inert storage alongside the story flags -- see transpile.INERT.
    import transpile
    # Engine variables with no established Genesis counterpart get inert
    # storage alongside the story flags -- see the note on INERT_UNKNOWN in
    # transpile.py for why that is safer than guessing an address.
    import correlate_vars  # noqa: F401  (kept for tooling parity)
    unmapped_engine = {a for a in named
                       if a not in transpile.VARIABLE_MAP
                       and a not in transpile.PROBABLE_MAP
                       and not any(lo <= a < hi for lo, hi, _ in transpile.WINDOW_MAP)}
    excluded = (named | DOS_ENGINE_EXTRA) - set(transpile.INERT) - unmapped_engine
    return [a for a, _ in counts.most_common() if a not in excluded], named


def build(rom: bytes, engine_used=None):
    """Return {dos_address: genesis_address} for every script-only flag."""
    if engine_used is None:
        engine_used = engine_addresses(rom)
    engine_used = set(engine_used) | mapped_targets()
    wanted, _named = matrix_flags()
    pool = ([a for a in countdown_flags(rom) if a not in engine_used]
            + region_gaps(rom, engine_used))
    if len(pool) < len(wanted):
        raise SystemExit(f"need {len(wanted)} flag slots, found {len(pool)}")
    # Busiest flags first, into the addresses Countdown itself used -- those
    # are the best-evidenced safe RAM in the region.
    return {dos: pool[i] for i, dos in enumerate(wanted)}

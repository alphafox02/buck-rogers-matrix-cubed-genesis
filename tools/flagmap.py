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
from pathlib import Path

import dax
import ecl
import genesis_disasm as G
import genesis_ecl

REPO = Path(__file__).resolve().parent.parent

WINDOWS = set(range(0x9AFC, 0x9B50)) | set(range(0x9BF6, 0x9C10))
REGION = range(0x9000, 0xA000)

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
    return sorted(a for a in seen if a not in CONFIRMED and a not in WINDOWS)


def region_gaps(rom: bytes, engine_used):
    """Unused addresses inside the region the engine devotes to script state."""
    table = G.load_opcodes()
    script = set()
    for _bid, code, _text in genesis_ecl.directory(rom):
        for ins in G.disassemble(genesis_ecl.decompress(code), table).values():
            for a in ins.args:
                if a.kind == "mem":
                    script.add(a.value)
    taken = script | set(engine_used) | WINDOWS | CONFIRMED
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
    excluded = named | DOS_ENGINE_EXTRA
    return [a for a, _ in counts.most_common() if a not in excluded], named


def build(rom: bytes, engine_used=()):
    """Return {dos_address: genesis_address} for every script-only flag."""
    wanted, _named = matrix_flags()
    pool = countdown_flags(rom) + region_gaps(rom, engine_used)
    if len(pool) < len(wanted):
        raise SystemExit(f"need {len(wanted)} flag slots, found {len(pool)}")
    # Busiest flags first, into the addresses Countdown itself used -- those
    # are the best-evidenced safe RAM in the region.
    return {dos: pool[i] for i, dos in enumerate(wanted)}

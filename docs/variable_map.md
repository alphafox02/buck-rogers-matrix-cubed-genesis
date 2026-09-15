# Variable Mapping: DOS to Genesis

The two engines keep their state in different places. DOS party flags sit
around `0x4C00`-`0x7F00`, the Genesis around `0x97xx`-`0x9Exx`. A transpiled
script therefore has correct structure but reads the wrong addresses until
they are translated.

## The job is much smaller than it looks

Matrix Cubed's scripts touch **418 distinct addresses**, which sounds
daunting. But they split into two very different groups:

| group | count | uses | what is needed |
|---|---|---|---|
| **engine-shared** | 50 | 3,448 | exact mapping — the engine reads these too |
| **script-only** | 368 | 6,286 | free reallocation — nothing but scripts touch them |

The 368 script-only addresses are story flags: quest state, doors opened,
NPCs spoken to. They are written and read **only by ECL**, so their numeric
addresses carry no meaning to the engine. They can be reallocated anywhere in
free Genesis flag space, as long as the allocation is consistent across every
block in the campaign.

**So the real work is 50 addresses, not 418.** Of those, sixteen account for
over 90% of engine-shared uses.

The classification comes from `ssi-engine`'s DOS configuration, which names
56 engine variables; Matrix Cubed uses 50 of them.

## Confirmed mappings

Found by correlating usage patterns that are forced by the engine's own
behaviour rather than by guesswork.

| role | DOS | Genesis | how it was established |
|---|---|---|---|
| `TEMP_START` — scratch | `0x7F79` | `0x9E6F` | dominant destination of `AND`/`OR` in both: 1,467 uses against 994. The next two scratch slots are consecutive in both (`0x7F7A`/`0x7F7B`, `0x9E70`/`0x9E71`). |
| `LAST_ECL` — current area | `0x4BF2` | `0x97E8` | the address each block compares against **its own id**: 63 DOS blocks, 25 of 27 Genesis blocks. |

## The engine-shared list, by usage

The sixteen that matter most, with their DOS addresses:

```
0x7F79  TEMP_START          1467      0x4C00  SAVED_TEMP_START     61
0xC04D  DUNGEON_DIR          325      0x7EC9  MOVEMENT_BLOCK       57
0xC04C  DUNGEON_Y            245      0x4CE6  MONEY_NEO_ACCT       53
0xC04B  DUNGEON_X            236      0x4BE6  DUNGEON_VALUE        46
0x7EC7  COMBAT_RESULT        111      0x7C2B  SEL_PC_CREDITS       40
0x7C00  SEL_PC_START         102      0x4BC3  OVERLAND_X           36
0x4BF2  LAST_ECL              86      0xC04F  MAP_SQUARE_INFO      33
0xC04E  MAP_WALL_TYPE         80      0x4CF6  FOR_LOOP_COUNT       31
0x7D00  SEL_PC_STATUS         77      0x4BF1  LAST_DUNGEON_Y       30
```

Each needs its Genesis counterpart found the same way the two confirmed ones
were: locate engine code that reads or writes the Genesis address and match
the role, or find a usage pattern the engine forces.

## Method that works

Correlate on behaviour the engine dictates, not on frequency alone:

- **self-reference** — a block comparing a variable against its own id can
  only be the current-area variable
- **operation role** — the overwhelmingly dominant destination of bitwise
  operations is the scratch register in both engines
- **consecutive banks** — scratch, party and combat variables sit in runs, so
  confirming one anchors its neighbours

Frequency rank alone is not sufficient: it agrees for the top two addresses
and diverges immediately after.

## Confirmed by targeted semantic tests

These rest on constraints the game's design forces, not on statistics.

| role | DOS | Genesis | evidence |
|---|---|---|---|
| `TEMP_START` scratch | `0x7F79` | `0x9E6F` | dominant destination of `AND`/`OR` in both (1,467 vs 994 uses); the next two slots are consecutive in both engines |
| `LAST_ECL` current area | `0x4BF2` | `0x97E8` | the address a block compares against **its own id** — 63 DOS blocks, 25 of 27 Genesis |
| `DUNGEON_DIR` | `0xC04D` | `0x9AFA` | compared against 0-3 and nothing else, evenly spread: DOS 89/86/72/69, Genesis 61/62/56/57. Only a direction produces that shape. |
| `DUNGEON_X` | `0xC04B` | `0x9AF6` | see below |
| `DUNGEON_Y` | `0xC04C` | `0x9AF7` | see below |

### Resolving which coordinate is which

Both variables top out at 15 on a 16x16 grid and are set together with the
direction at area entry, so usage alone cannot separate them. The maps can.

Scripts place the party at a known square on entry. Read the pair one way
and the party stands somewhere walkable; read it the other way and it stands
inside a wall. Testing every area's entry position against that area's own
extracted map:

| reading | start squares walkable | total walls at start positions |
|---|---|---|
| `0x9AF6` = X, `0x9AF7` = Y | **15 of 16** | **23** |
| reversed | 11 of 16 | 39 |

A party starting sealed inside a four-walled box would be a bug, and the
shipped game does not have five of them. The first reading is correct.

This works because the map decoder is already confirmed — it is one verified
piece of the project being used to verify another.

## Two windows are not plain addresses

The ECL address resolver at `0x042E0` special-cases two ranges, redirecting
them into per-character records indexed by the selected character at
`$9DA7`:

```
042E0  cmpa.l #$FFFF9AFC,a0     ; window 1 lower bound
042E8  cmpa.l #$FFFF9B50,a0     ; upper bound
042F0  adda.w #$1F6C,a0
042F6  move.b ($9DA7).w,d0      ; selected character
042FA  mulu.w #$D6,d0           ; 214 bytes per character record
042FE  adda.w d0,a0

04302  cmpa.l #$FFFF9BF6,a0     ; window 2
0430A  cmpa.l #$FFFF9C10,a0
04312  adda.w #$287A,a0
0431C  mulu.w #$1A,d0           ; 26 bytes per character
```

Every other address passes through unchanged as plain RAM.

These windows are the Genesis counterparts of the DOS `SEL_PC_*` block:

| DOS | span | Genesis | span |
|---|---|---|---|
| `SEL_PC_START` `0x7C00`-`0x7C4C` | 77 | `0x9AFC`-`0x9B4F` | 84 |
| `SEL_PC_STATUS` `0x7D00`-`0x7D19` | **26** | `0x9BF6`-`0x9C0F` | **26** |

The second is an exact size match, and both are contiguous windows indexed
per character in each engine. This was read off the engine rather than
inferred from usage, so it is firmer evidence than a signature match.

**Consequence for flag reallocation:** relocated script flags must avoid
both windows, or they will be silently redirected into character data.

## Finding the rest: what the engine writes and scripts read

An engine-shared variable is by definition one the **engine writes and
scripts read**. Disassembling every absolute-short write in the ROM's code
and intersecting with script reads gives exactly 20 addresses — a
candidate set two orders of magnitude smaller than the 259 variables scripts
touch, and it contains all six mappings confirmed earlier, which is a useful
check on the method.

Each is then pinned by a value signature the engine forces.

| role | DOS | Genesis | evidence |
|---|---|---|---|
| `MAP_SQUARE_INFO` | `0xC04F` | `0x9AF9` | the engine fills it at `0x04210` with `(X*16 + Y)` indexed into a map plane. Both sides are dominated by the value 63 — 32 uses against 31 — because scripts mask the info byte with `0x3F`. |
| `MAP_WALL_TYPE` | `0xC04E` | `0x97AD` | both top out at exactly **12**, the highest wall type these maps use, across 19 and 80 uses. |
| `COMBAT_RESULT` | `0x7EC7` | `0x9DBD` | tested against 128 in 11 of 11 Genesis uses and 107 of 111 DOS uses. |
| `MOVEMENT_BLOCK` | `0x7EC9` | `0x9DBF` | holds 255 in **63 of 63** Genesis uses and **57 of 57** DOS uses. |
| `INDEX_OF_SEL_PC` | `0x7EB1` | `0x9DA7` | read straight off the address resolver at `0x042E0`, which multiplies it by the character record size. |

The map lookup at `0x04210` is worth reading in full, because it confirms
three mappings at once:

```
04212  move.b  $9AF6.w,d0        ; X
04216  asl.w   #4,d0             ; * 16
04218  add.b   $9AF7.w,d0        ; + Y
0421C  lea.l   $B7A4.w,a0        ; a map plane
04220  move.b  (a0,d0.w),$9AF9.w ; the square's value
```

X, Y and the per-square value, in five instructions.

## Coverage

**94.7% of the 10,019 variable references now translate**, leaving 536
across 33 addresses.

## Statistical candidates

`tools/correlate_vars.py` builds a behavioural signature per variable —
which opcodes touch it and in which operand position, the distribution of
immediates it meets, and the largest value it ever holds — then matches
signatures across engines and assigns greedily so no address is used twice.

It independently reproduces `TEMP_START` and `LAST_ECL` as top matches,
which is a useful check on the method. Its strongest unverified suggestions:

| score | DOS | name | Genesis |
|---|---|---|---|
| 1.000 | `0x7EC9` | `MOVEMENT_BLOCK` | `0x9DBF` |
| 0.978 | `0x7EC7` | `COMBAT_RESULT` | `0x9DBD` |
| 0.947 | `0x4C00` | `SAVED_TEMP_START` | `0x9852` |
| 0.867 | `0x4BC4` | `OVERLAND_Y` | `0x9801` |
| 0.862 | `0x7EC6` | `COMBAT_MORALE_BASE` | `0x9DBC` |
| 0.812 | `0x7D19` | `SEL_PC_HP_CURR` | `0x97FE` |
| 0.761 | `0xC04E` | `MAP_WALL_TYPE` | `0x97AD` |

**Treat these as leads.** The correlator disagrees with the targeted test on
`DUNGEON_DIR`, and wanted the same Genesis address for both `DUNGEON_X` and
`DUNGEON_Y` before unique assignment forced them apart. A high score means
two variables are used similarly, which is necessary but not sufficient.

Each candidate still needs confirming the way the four above were: find a
constraint only the correct variable can satisfy, or locate engine code that
reads the Genesis address and read off its role.

## Status

Four of fifty confirmed, seven more with strong candidates. Script-only
reallocation is not yet implemented in `tools/transpile.py`, which passes all
addresses through unchanged — which is why transplanted scripts execute with
correct structure and incorrect addressing.

---

## Flag reallocation — implemented

`tools/flagmap.py` places Matrix Cubed's 360 script-only flags into Genesis
RAM. This is not an optimisation: **255 of them sit below `0x8000` in DOS**,
and Genesis ECL addresses are used as 68000 absolute-short operands, which
sign-extend. A DOS flag at `0x4C54` becomes `0x00004C54` — ROM — and the
write vanishes.

### Where they go

Two sources, preferred in order:

1. **The flags Countdown itself uses** (193 addresses). We are replacing its
   campaign, so its story flags are free — and they are the best-evidenced
   safe RAM available, because the shipped game keeps its own flags there.
2. **Gaps inside the same region** (3,786 more). Addresses in
   `0x9000`-`0x9FFF` touched by neither Countdown's scripts nor its engine.

Free-looking RAM *elsewhere* was rejected deliberately. Detection of engine
use relies on absolute-short operands and cannot see access through a
register, so distance from known-used addresses is not evidence of safety;
being inside the range the engine devotes to script state is.

Both per-character windows are excluded — the resolver would silently
scatter a flag placed there across the party.

### Coverage

**91.8% of the 10,019 variable references in Matrix Cubed's scripts now
translate correctly**, leaving 821 across 38 addresses.

| source | references |
|---|---|
| script-only flags, reallocated | most of the 8,755 |
| confirmed engine variables | scratch bank, area, position, direction |
| character windows | mapped as ranges |
| **still unmapped** | **821 (8.2%)** |

### Two bugs this surfaced

**The allocator was reassigning live engine registers.** The configuration
names `TEMP_START` at `0x7F79` and says nothing about the slots after it,
but `0x7F7A` onward are the same scratch bank — that is how the mapping was
confirmed in the first place. They were being handed out as free story
flags. Banks are now excluded as ranges.

**Jump operands were being classified by instruction, not by position.**
`GOTO` and `GOSUB` take a single target, but `ON_GOTO` and `ON_GOSUB` take a
**selector variable**, a count, and only then a tail of targets. Treating
every operand of a branching instruction as an address rewrote the selector
as though it were code. Operand roles are now per-position.

---

## Confidence tiers, and why a probable mapping is still applied

Mappings are kept in two tables.

**`VARIABLE_MAP`** holds those pinned by a constraint that admits only one
answer — a value distribution only a direction produces, a maximum only a
wall nibble reaches, an address the engine itself indexes by.

**`PROBABLE_MAP`** holds those supported by good evidence that nonetheless
does not exclude every alternative. Currently one: `FOR_LOOP_COUNT`
`0x4CF6` → `0x98EC`, the only non-scratch operand of `LOAD_CHAR` /
`LOADCHARACTER` on either side, 27 uses against 10.

These are **applied**, which deserves justification, because leaving a
mapping out is not the conservative choice here. An unmapped DOS address
below `0x8000` sign-extends into ROM: the write is silently discarded, and a
party loop reading it never advances. A wrong RAM address at least fails
visibly, in one place, and is cheap to revisit. Silence is the worse failure
mode.

Keeping the two tables separate means a later contradiction costs one line.

## Coverage

**95.0%** of 10,019 variable references translate. 505 remain across 32
addresses, led by:

| DOS | name | uses |
|---|---|---|
| `0x4C00` | `SAVED_TEMP_START` | 61 |
| `0x4CE6` | `MONEY_NEO_ACCT` | 53 |
| `0x4BE6` | `DUNGEON_VALUE` | 46 |
| `0x4BC3` | `OVERLAND_X` | 36 |
| `0x4BF1`/`0x4BF0` | `LAST_DUNGEON_Y`/`X` | 59 |
| `0x4BE7`-`0x4BE9` | `ENGINE_CONF_*` | 84 |

`MONEY_NEO_ACCT` resisted the usual approach. It is distinctive on the DOS
side — compared and subtracted against 10000, 20000, 2000 — but the Genesis
side has no variable with that signature. The two variables used with large
constants there both belong to the scratch bank. Either Countdown's scripts
handle money without large literals, or it lives somewhere the
engine-writes/scripts-read intersection does not reach.

---

## The combat/party bank: one constant offset

The breakthrough. `COMBAT_MORALE_BASE` was found by value signature — DOS
writes `{80, 90, 100}` and Genesis `0x9DBC` writes `{80, 90, 100}` — and it
landed next to two mappings already confirmed:

```
DOS 0x7EC6 -> 0x9DBC   morale
DOS 0x7EC7 -> 0x9DBD   combat result
DOS 0x7EC9 -> 0x9DBF   movement block
```

A constant offset of `0x1EF6`. Testing it against everything else already
known:

| DOS | Genesis | how it was originally established |
|---|---|---|
| `INDEX_OF_SEL_PC` `0x7EB1` | `0x9DA7` | read off the address resolver at `0x042E0` |
| `COMBAT_RESULT` `0x7EC7` | `0x9DBD` | tested against 128 on both sides |
| `MOVEMENT_BLOCK` `0x7EC9` | `0x9DBF` | 255 in 63/63 and 57/57 uses |
| `TEMP_START` `0x7F79` | `0x9E6F` | dominant `AND`/`OR` destination |

**All four land on the offset.** Two came from engine disassembly and two
from script usage, so the agreement is not an artefact of one method. The
region `0x7E00`-`0x7FFF` is a single bank the port relocated wholesale.

It does **not** extend lower: `0x7C00 + 0x1EF6` would be `0x9AF6`, which is
`DUNGEON_X`, whereas the resolver places `SEL_PC_START` at `0x9AFC`. The
character records were moved separately.

## Coverage

**97.81%** of 10,019 variable references, and — the number that actually
matters — **15 of 33 blocks are now fully translatable**, meaning every
reference in them resolves. Those blocks are not small: 846, 871, 946 and
1,036 instructions among them.

A block needs *every* reference mapped to behave correctly, so overall
percentage flatters the position. Blocks-at-100% is the honest metric.

Remaining blockers, by how many blocks each holds back:

| DOS | name | blocks |
|---|---|---|
| `0x4D7C` | `ENEMY_WAS_ENTERED` | 6 |
| `0x4CE6` | `MONEY_NEO_ACCT` | 4 |
| `0x4C1A` | `REPAIR_COST` | 3 |
| `0x4BC9`/`0x4BC3`/`0x4BC4` | `TIME_HOUR`, `OVERLAND_X/Y` | 2 each |

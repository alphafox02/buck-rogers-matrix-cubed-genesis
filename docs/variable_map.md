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

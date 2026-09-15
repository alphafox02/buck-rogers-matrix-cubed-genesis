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

## Status

Two of fifty confirmed. Script-only reallocation is not yet implemented in
`tools/transpile.py`, which currently passes all addresses through unchanged
— which is why transplanted scripts execute with correct structure and
incorrect addressing.

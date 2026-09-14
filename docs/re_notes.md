# Reverse-Engineering Notebook

Confidence labels: CONFIRMED / HIGH CONFIDENCE / PROBABLE / SPECULATIVE / UNKNOWN

---

## Genesis ROM identification — CONFIRMED

| field | value |
|---|---|
| file | `Buck Rogers - Countdown to Doomsday (USA, Europe).gen` |
| size | 1,048,576 bytes (1 MB) |
| SHA-256 | `997cbd682bc7c0636302f07219d9152244c8ae06028fd7d91463d35756630ce5` |
| console | `SEGA GENESIS` |
| copyright | `(C)T-50 1991.DEC` |
| title | `BUCK RODGERS COUNTDOWN TO DOOMSD` (misspelled in the ROM) |
| serial | `GM T-50286 -00` |
| region | `U` |
| I/O support | `J` (3-button joypad) |
| ROM range | `0x000000`–`0x0FFFFF` |
| RAM range | `0xFF0000`–`0xFFFFFF` |

### No SRAM declared — CONFIRMED, consequences UNKNOWN

The external RAM field at `0x1B0` is blank — no `RA` signature, so the
header declares no battery-backed save. Yet the ROM contains the string
`"save game"` at `0x122FD`.

Open question: does the game use undeclared SRAM (common, and tolerated by
most emulators), or a password system? This matters because "stable saves"
is a stated project goal. **Resolve early.**

### Free space — CONFIRMED

Largest constant run is 57,304 bytes of `0x00` at `0xF1FD8` to EOF. The rest
of the ROM is essentially full. Matrix Cubed is a larger campaign than
Countdown, so the ROM will need to grow.

The Genesis addresses up to 4 MB linearly with no mapper hardware, so
`0x100000`–`0x3FFFFF` is available without banking. Whether the engine's
resource loader uses full 32-bit ROM pointers is **UNKNOWN** and should be
checked before planning around it.

---

## The Genesis port runs the Gold Box ECL engine — HIGH CONFIDENCE

This is the single most important finding so far. The Genesis version is not
a bespoke console reimplementation; it is the Gold Box engine with a
console presentation layer.

### Evidence

A table of **94 ECL opcode mnemonics** in plain ASCII at `0x452A`–`0x482D`,
preceded by what appears to be a 16-bit offset table at `0x4500`:

```
EXIT GOTO GOSUB COMPARE ADD SUBTRACT DIVIDE MULTIPLY RANDOM SAVE
LOADCHARACTER LOADMONSTER SETUPMONSTERS APPROACH PICTURE INPUTNUMBER
INPUTSTRING PRINT PRINTCLEAR RETURN COMPAREAND MENU IFEQ IFNE IFLT IFGT
IFLE IFGE CLEARMONSTERS SETTIMER CHECKPARTY SPACECOMBAT NEWECL LOADFILES
SKILL PRINTSKILL COMBAT ONGOTO ONGOSUB TREASURE ROB CONTINUE GETABLE
HMENU GETYN DRAWINDOW DAMAGE AND OR WHMENU FINDITEM PRINTRETURN CLOCK
SAVETABLE ADDNPC LOADPIECES PROGRAM WHO DELAY SPELLS PROTECT CLEARBOX
DUMP JOURNAL DESTROY ADDEP ENCEXIT SOUND SAVECHARACTER HOWFAR FOR ENDFOR
HIDEITEMS SKILLDAMAGE DUEL STORE VIEW ANIMATE STAIRCASE HALFSTEP
STEPFORWARD PALETTE UNLOCKDOOR ADDFIGURE ADDCORPSE ADDFIGURE2 ADDCORPSE2
UPDATEFRAME REMOVEFIGURE EXPLOSION STEPBACK HALFBACK NEWREGION ICONMENU
```

Supporting engine strings:

| offset | string |
|---|---|
| `0x3324` | `Bad ECL address` |
| `0x40EA` | `cant load ecl` |
| `0x12651` | `debug ecl` |
| `0x57BE` | `Could not find geo!` |
| `0xB7A2` | `LoadBigPic failed` |
| `0x9D02` | `loadpieces error 1` |
| `0x220C` | `compression overflow` |
| `0x493E` | `couldnt load monster` |
| `0x9288` | `Sprites freed out of order` |
| `0x12EB0` | `Enter wallset as decimal (1,4,7..)` |
| `0x12E31` | `pic~sq+~sq-~fr+~fr-~fig~pal~quit` |

`"Could not find geo!"` corresponds to `GEO1.DAX` in the DOS distribution.
`LOADPIECES` corresponds to `8X8D1.DAX` / `WALLDEF1.DAX`. The resource
vocabulary is shared between the DOS and Genesis versions.

### A developer debug menu survives in the retail ROM — HIGH CONFIDENCE

`"debug ecl"`, `"view items"`, `"How many items?"`,
`"Enter wallset as decimal"` and a mode string
`"pic~sq+~sq-~fr+~fr-~fig~pal~quit"` are all present.

If this can be triggered, it is a very large accelerator. **UNKNOWN** how to
activate it — likely a RAM flag or controller combination.

### Grid-step movement survives the isometric change — PROBABLE

The opcode table includes `STEPFORWARD`, `HALFSTEP`, `STEPBACK`,
`HALFBACK` and `STAIRCASE`. These imply the DOS games' grid-step navigation
model was retained and only the camera changed.

If true, Matrix Cubed map data transfers as a conversion rather than a
redesign. **This has not been verified in the running game and is the single
assumption most worth testing early.**

---

## DOS Countdown and DOS Matrix Cubed are the same engine build — CONFIRMED

Derived by diffing the two game configs in `farmboy0/ssi-engine`
(`src/main/resources/Buck Rogers - *.properties`).

Complete list of differences:

- `detection.md5`
- four umlaut glyph definitions
- title screen layout offsets (`title.3`)
- `mode.name`, `mode.DEMO`
- `uses.SPECIAL_CHARS_NOT_FROM_FONT`
- `overland.map` picture IDs: `113,114` → `112,116`
- `rule.starting_level`: `2` → `7`

The `# Used OpCodes` block is **identical**. The ~70 documented engine RAM
addresses are **identical**. `character.format`, `character.values` and
`rule.flavor` are all `BUCK_ROGERS` for both.

**Implication:** any tool that reads Countdown's DOS data reads Matrix
Cubed's data, and the ECL dialect is shared between them.

---

## Genesis vs DOS ECL opcode alignment — PROBABLE

Positional comparison of the Genesis mnemonic table against the DOS opcode
enum in `ssi-engine` (`engine/script/EclOpCode.java`, 102 entries with
explicit opcode numbers):

| opcode | Genesis | DOS |
|---|---|---|
| `0x00` | `EXIT` | `EXIT` |
| `0x01` | `GOTO` | `GOTO` |
| `0x03` | `COMPARE` | `COMPARE` |
| `0x09` | `SAVE` | `WRITE_MEM` |
| `0x0A` | `LOADCHARACTER` | `LOAD_CHAR` |
| `0x0C` | `SETUPMONSTERS` | `SPRITE_START` |
| `0x0D` | `APPROACH` | `SPRITE_ADVANCE` |
| `0x15` | `MENU` | `MENU_VERTICAL` |
| `0x1C` | `CLEARMONSTERS` | `CLEAR_MON` |

Opcodes `0x00`–`0x1C` align in exact order and meaning — 29 consecutive
matches, including non-obvious ones where SSI's internal name differs from
the reverse-engineered name (`SAVE` = `WRITE_MEM`).

Past `0x1D` the tables drift by a few slots, but the sequence still tracks:
`SPACE_COMBAT → NEW_ECL → ... → SKILL → COMBAT → ON_GOTO → ON_GOSUB →
TREASURE` appears in both.

**Not yet verified:** the actual dispatch table behind the Genesis mnemonics
has not been located, so the numbering above is inferred from the order of
the name strings. Confirming it is the next Genesis-side task.

---

## Open questions, ranked

1. Where is the Genesis ECL opcode dispatch table, and does the numbering
   match DOS?
2. How is the leftover `debug ecl` menu triggered?
3. Does the Genesis resource loader use 32-bit ROM pointers (can the ROM
   grow past 1 MB)?
4. Saves: undeclared SRAM, or passwords?
5. Is the map model really grid-step, with only the camera changed?
6. Which Matrix Cubed opcodes have no Genesis equivalent?

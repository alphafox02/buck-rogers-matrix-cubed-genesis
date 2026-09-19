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

---

## The Genesis port ADDED substantial engine features — HIGH CONFIDENCE

An earlier draft of this file overstated how similar the two engines are.
A proper set-difference between the Genesis mnemonic table and the DOS
opcode enum (allowing for 40 justified name equivalences such as
`SAVE`/`WRITE_MEM`) gives **32 Genesis-only** and **33 DOS-only** opcodes.

The Genesis-only set is not random. It clusters:

**Animated isometric figures — the console exploration/combat layer**
`ADDFIGURE` `ADDFIGURE2` `ADDCORPSE` `ADDCORPSE2` `UPDATEFRAME`
`REMOVEFIGURE` `ANIMATE` `EXPLOSION`

**Stepped movement with intermediate frames**
`STEPFORWARD` `STEPBACK` `HALFSTEP` `HALFBACK` `STAIRCASE` `HOWFAR`

The presence of *half* steps is the giveaway: DOS moved a full grid square
at a time, the Genesis animates between squares.

**Console UI**
`ICONMENU` `DRAWINDOW` `WHMENU` `VIEW` `PALETTE`

**A real save system**
`SAVECHARACTER` `SAVETABLE` `GETABLE` `DUMP`

This is relevant to the blank SRAM header field — the Genesis port clearly
implements saving at the script level.

**Gameplay additions**
`DUEL` `SKILLDAMAGE` `UNLOCKDOOR` `HIDEITEMS` `ENCEXIT` `NEWREGION`
`SETTIMER` `CONTINUE` `SOUND`

### The DOS-only set is the actual risk list

These exist in the DOS engine — and therefore potentially in Matrix Cubed's
scripts — with no obvious Genesis counterpart:

`PARLAY` `SURPRISE` `ENCOUNTER_MENU` `SELECT_ACTION` `NPC_FIND`
`NPC_REMOVE` `HAS_EFFECT` `PRINT_RUNES` `LOGBOOK_ENTRY` `TREASURE_MULTICOIN`
`TREASURE_MULTICOIN4` `CALL` `COPY_MEM` `WRITE_MEM_BASE_OFF` `RANDOM0`
`PICTURE2` `CLOCK2` `PARTY_STRENGTH` `SPRITE_OFF` `STOP_MOVE_23`
`LOAD_AREA_MAP_DECO` `SOUND_EVENT_2C` `SOUND_EVENT_43` plus several
unidentified (`GTTSF_32`, `GTTSF_40`, `POD_29`, `INPUT_RETURN_*`).

`PARLAY` (conversation/negotiation) and `SURPRISE` are the notable
gameplay losses; the rest are largely plumbing.

### What this means

The brief's Phase 6 ("Deal With Rule Differences") now has a concrete
starting table rather than a hypothetical one. Each DOS-only opcode needs a
decision: translate, reimplement in 68k, edit the scenario, or drop.

**Crucially, this list is a worst case.** It counts opcodes the DOS *engine*
supports, not opcodes *Matrix Cubed actually uses*. Disassembling
`ECL1.DAX` converts "33 orphans" into "N real call sites", which is the
number that actually determines difficulty. That is the next task.

### On space combat specifically

`SPACECOMBAT` exists in both engines at the same position, so the
script-level hook for ship fights transfers directly. The *presentation*
is Genesis-specific and lives below the ECL layer — which is exactly what
we want, since the goal is to reuse the console presentation.

---

## Matrix Cubed ECL disassembled — the feasibility number

`tools/ecl.py` + `tools/dump_ecl.py` decode `ECL1.DAX`:

- **21,513 instructions** across 33 blocks
- **71 distinct opcodes** actually used
- **83.1%** of 247,573 bytes decoded on a linear pass

The remaining 17% is mostly blocks where linear decoding starts inside a
data region (`0x99` appears as a bogus opcode at low offsets in blocks 36,
48, 49, 64, 65 and 81). Those blocks need a proper entry-point header,
which has not been located yet. Blocks that stop at ~99.8% are simply
hitting trailing data at the end of the code, which is expected.

Sample output (block 17), showing the decode is genuinely correct:

```
000F8  PRINT_CLEAR   "THE AIRLOCK IS SEALED."
0010D  PICTURE       98
00110  SOUND_EVENT   63
00113  PRINT_CLEAR   "SCOT.DOS WELCOMES YOU BACK TO YOUR SHIP. '"
00136  ON_GOTO       [0x4C2C], 5, {[0x8180], [0x8149], [0x8149], [0x81C4], [0x8225]}
0014B  COMPARE       [0x4C07], 2
00151  IF_EQUALS
00152  GOTO          [0x8429]
```

### Orphan opcodes — CONFIRMED, and the news is good

Cross-referencing the 71 opcodes Matrix Cubed actually uses against the 94
Genesis mnemonics (with 60+ justified name equivalences):

| opcode | uses | share |
|---|---|---|
| `INPUT_RETURN` | 1551 | 7.21% |
| `CALL` | 142 | 0.66% |
| `PICTURE2` | 111 | 0.52% |
| `COPY_MEM` | 111 | 0.52% |
| `SELECT_ACTION` | 77 | 0.36% |
| `UNKNOWN_44` | 19 | 0.09% |
| `UNKNOWN_4B` | 18 | 0.08% |
| `UNKNOWN_48` | 6 | 0.03% |
| `UNKNOWN_4A` | 5 | 0.02% |
| `NPC_REMOVE` | 4 | 0.02% |
| `RANDOM0` | 3 | 0.01% |
| `WRITE_MEM_BASE_OFF` | 2 | 0.01% |
| `UNKNOWN_49` | 1 | 0.00% |

**13 distinct orphans, 9.53% of all instructions.**

`INPUT_RETURN` alone is 1,551 of those 2,050 uses — and it is almost
certainly trivial ("press return to continue"); the Genesis equivalent is
likely folded into `PRINTRETURN` or handled entirely by the UI layer.
Discount it and the orphan share drops to **2.3%**, concentrated in four
opcodes: `CALL`, `PICTURE2`, `COPY_MEM`, `SELECT_ACTION`.

Note also that `PARLAY` and `SURPRISE` — flagged earlier as the notable
gameplay losses — **do not appear in Matrix Cubed at all.** Those opcode
slots (`0x2C`, `0x23`) resolve to `INPUT_YES_NO` and `SKILL_CHECK` in the
Buck Rogers games.

### Interpretation

The worst case was "33 DOS opcodes with no Genesis counterpart". The actual
case is 13, of which one dominates and is probably trivial, and four
matter. That is a very short list to either reimplement in 68k or work
around in the scenario.

This was the project's central feasibility gate. It is now largely cleared
on the DOS side. **The remaining risk has moved to the Genesis side**,
which is still almost entirely unexplored: the ROM's resource layout, map
format, text encoding and ECL dispatch table are all UNKNOWN.

---

## The Genesis ECL virtual machine — CONFIRMED

Located and decoded. This is the heart of the engine.

### Main dispatch loop at `0x03344`

```
03344: 72 00              moveq   #0,d1
03346: 12 1a              move.b  (a2)+,d1        ; fetch opcode; a2 = ECL program counter
03348: 2e 01              move.l  d1,d7           ; d7 = current opcode
0334A: 4a 38 9b b9        tst.b   ($FF9BB9).w     ; debug trace flag
0334E: 67 04              beq.s   +4
03350: 61 00 10 3a        bsr     $0438C          ; print opcode name (debug tracer)
03354: 32 07              move.w  d7,d1
03356: e3 41              asl.w   #1,d1           ; opcode * 2
03358: 47 f9 00 00 33 6e  lea     $0000336E,a3    ; dispatch table
0335E: 32 33 10 00        move.w  (a3,d1.w),d1    ; 16-bit self-relative offset
03362: 4e b3 10 00        jsr     (a3,d1.w)       ; call handler
03366: 60 a0              bra.s   $03308          ; loop
```

A textbook bytecode VM. Registers: **`a2` is the ECL program counter**,
**`d7` holds the current opcode**.

### Key addresses

| address | meaning |
|---|---|
| `0x0336E` | **opcode dispatch table** — 94 entries, 16-bit big-endian, self-relative to `0x336E` |
| `0x0342A` | first handler (`EXIT`); also the exact end of the dispatch table |
| `0x0446E` | **opcode name table** — 94 entries, 16-bit big-endian, self-relative to `0x446E` |
| `0x0452A` | opcode name strings, NUL-terminated |
| `0x03324` | `"Bad ECL address"`, printed via `lea $3324,a0 / jsr $132A6` |
| `0x0438C` | debug opcode-name printer |
| `0x011DC4` | large monotonic 16-bit self-relative pointer table into `0x120D6`+ — **probable main text/string pointer table**, not yet confirmed |

The dispatch table is exactly 94 entries: `0x336E + 94*2 = 0x342A`, which is
precisely where the first handler begins. So the Genesis ECL has exactly
**94 opcodes, numbered 0x00–0x5D**.

### The debug tracer is one RAM byte — HIGH CONFIDENCE

`tst.b ($FF9BB9).w` before every instruction dispatch. If RAM `$FF9BB9` is
non-zero, the VM prints the mnemonic of each opcode before executing it.

**Setting one byte in RAM turns the retail ROM into an ECL instruction
tracer.** This should be the first thing tested in an emulator — it makes
the entire scripting layer observable without any patching.

---

## Genesis vs DOS opcode numbering — CONFIRMED

Full 94-entry comparison (see `docs/opcode_map.md` for the table):

- **`0x00`–`0x1C`: a perfect 29-opcode run.** Identical numbering and
  meaning, including `SAVE` = `WRITE_MEM` and `SETUPMONSTERS` =
  `SPRITE_START` where SSI's internal name differs from the
  reverse-engineered one.
- **First divergence at `0x1D`.** Genesis `SETTIMER` vs DOS
  `PARTY_STRENGTH`.
- **60 of 77 shared slots align; 17 differ.**
- **`0x4D`–`0x5D` are Genesis-only** — the 17 console additions
  (`ANIMATE`, `STAIRCASE`, the `ADDFIGURE`/`ADDCORPSE` family, `PALETTE`,
  `ICONMENU`, the step/half-step movement opcodes).

### What this means for the port

Several "mismatches" are renumbering, not loss. Genesis `0x22`/`0x23` are
`SKILL`/`PRINTSKILL` where DOS has `PARTY_SKILL_CHECK`/`SKILL_CHECK` — the
same pair, swapped. Others are plausible semantic equivalents under
different names: Genesis `GETABLE` (`0x2A`) against DOS `COPY_MEM`,
`SAVETABLE` (`0x35`) against `WRITE_MEM_BASE_OFF`.

**Conclusion: an ECL transpiler is required — the numbering genuinely
differs past `0x1C` — but it is a table remap, not a rewrite.** Combined
with the earlier finding that only 13 opcodes used by Matrix Cubed lack a
Genesis counterpart (and one of those is 76% of the orphan uses), the
scenario-translation problem is now well-bounded.

---

## The debug tracer is a single-step ECL debugger — HIGH CONFIDENCE

Decoding the routine at `0x0438C` (called from the VM loop whenever RAM
`$FF9BB9` is non-zero) shows it is not a simple logger. It:

1. Saves the current text cursor state
2. Opens a window at roughly `(0x02, 0x1B)`–`(0x26, 0x1C)` — a two-line
   strip at the bottom of the screen
3. Prints `a2 - 1`, the **address of the instruction about to execute**
   (via `jsr $133B4`, a hex-long printer)
4. Prints the **next six bytes** at `(a2)` through `5(a2)` as hex
   (`jsr $133AA`, a hex-byte printer, with `jsr $11CA0` between for spacing)
5. Looks up `d7` in the name table at `0x446E` and prints the **mnemonic**
   (`jsr $11CA4`)
6. `bsr $06C66`, then `btst #5,d0` / `beq` — **loops until a button is
   pressed**
7. Restores the cursor state and returns

So with one RAM byte set, the retail ROM displays a live disassembly line
for every ECL instruction and waits for a button press between each.

**This is a single-step script debugger that SSI left in the shipped
cartridge.** It gives us:

- live confirmation of our opcode numbering, for free
- the ability to watch any scripted scene execute instruction by instruction
- ground truth for the argument encoding, by comparing the six raw bytes
  against our own disassembler's output

It is the single highest-leverage thing found so far, and it requires no
patching — only a memory write.

### How to reach it

`$FF9BB9` is presumably set by a menu option (`"debug ecl"` appears at ROM
`0x12651`). Either route works:

- find and trigger the menu, or
- write the byte directly from an emulator debugger

The second is easier and is the plan.

---

## Genesis ECL argument encoding — CONFIRMED, and it is identical to DOS

The `GOTO` handler at `0x3438` calls `bsr $0404A`. That routine is the
shared argument fetcher for every opcode. Decoded:

```
0404A: 10 1a           move.b  (a2)+,d0          ; read the TYPE byte
0404C: 12 00           move.b  d0,d1
0404E: 42 b8 d5 f8     clr.l   ($FFD5F8).w       ; clear 32-bit accumulator
04052: 11 da d5 fb     move.b  (a2)+,($FFD5FB).w ; payload byte 0 -> LSB
04056: 4a 01           tst.b   d1
04058: 67 12           beq.s   $0406C            ; type 0 -> 1 byte, done
0405A: 11 da d5 fa     move.b  (a2)+,($FFD5FA).w ; payload byte 1
0405E: b2 3c 00 04     cmp.b   #4,d1
04062: 66 08           bne.s   $0406C            ; type != 4 -> 2 bytes, done
04064: 11 da d5 f9     move.b  (a2)+,($FFD5F9).w ; payload byte 2
04068: 11 da d5 f8     move.b  (a2)+,($FFD5F8).w ; payload byte 3
0406C: 4a 01           tst.b   d1
0406E: 6b 3a           bmi.s   $040AA            ; type & 0x80 -> string
04070: 08 01 00 00     btst    #0,d1
04074: 67 2e           beq.s   $040A4            ; type & 0x01 clear -> immediate
04076: 70 ff           moveq   #-1,d0
04078: 30 38 d5 fa     move.w  ($FFD5FA).w,d0    ; else treat as memory address
0407C: 20 40           movea.l d0,a0
0407E: 61 00 02 60     bsr     $042E0            ; resolve address
...
040AA: b2 3c 00 80     cmp.b   #$80,d1
040AE: 66 0c           bne.s   $040BC
040B0: 20 38 d5 f8     move.l  ($FFD5F8).w,d0
040B4: d0 b8 b9 a4     add.l   ($FFB9A4).w,d0    ; + ECL base -> string pointer
040B8: 20 40           movea.l d0,a0
040BA: 4e 75           rts
```

### The rules are the same as the DOS engine

| type | payload | meaning |
|---|---|---|
| `0x00` | 1 byte | immediate |
| `0x04` | 4 bytes | immediate long |
| anything else | 2 bytes | immediate or address |
| bit 0 set | — | value is a **memory address**, resolved via `$042E0` |
| bit 7 set | — | value is a **string** |

This is exactly the DOS scheme. The type-byte semantics, the size rules and
the address/string flag bits all carry over unchanged.

### Two details that matter

**Arguments are stored little-endian.** Payload bytes are written LSB-first
(`$FFD5FB`, then `$FFD5FA`, `$FFD5F9`, `$FFD5F8`) on a big-endian CPU. The
Genesis port kept the DOS byte order in the bytecode rather than
byte-swapping the data — strong evidence the scenario data was carried
across from the DOS toolchain essentially as-is.

**Strings moved out of line.** In DOS, type `0x80` is an *inline* packed
string (a length byte followed by 6-bit packed characters). On the Genesis,
type `0x80` is an *offset* added to the ECL base pointer at `$FFB9A4` —
the text was pulled out into a separate pool, which is the sensible choice
for a cartridge.

### Why this matters

Combined with the opcode mapping, the scenario translation problem is now
fully characterised:

1. **Opcodes** — remap through a table; `0x00`–`0x1C` is already identical
2. **Arguments** — no change needed; same types, same sizes, same byte order
3. **Strings** — the one real transformation: extract inline strings and
   emit them into a pool, rewriting the argument to an offset

That is a well-understood compiler back-end, not a research problem.

### Other addresses learned

| address | meaning |
|---|---|
| `$FFB9A4` | ECL base pointer (added to string offsets) |
| `$FFD5F8`–`$FFD5FB` | 32-bit argument accumulator, little-endian |
| `0x042E0` | memory-address resolver |
| `0x0404A` | argument fetch routine |
| `0x040EA` | `"cant load ecl"` error path |

---

## Emulator status

BlastEm 0.6.3.4 is installed and runs the ROM at full speed. Two notes for
whoever picks this up:

- **The naive tracer patch hangs the game.** `tools/patch_rom.py trace`
  NOPs the branch at `0x0334E` so the tracer always fires. Because the
  tracer waits for a button press on *every* instruction, and ECL runs
  before the screen is set up, the result is a black screen. A usable
  version must also patch out the button-wait loop at the end of `0x0438C`,
  or set `$FF9BB9` at the right moment from a debugger instead.
- **`pkill -f blastem` will kill your own shell** if the command line
  containing that pattern is still running. Use `pkill -x blastem`.

`tools/patch_rom.py` verifies the original bytes before patching and fixes
up the Genesis header checksum at `0x18E`. Its checksum routine reproduces
the stock ROM's `0xD7B6` exactly, so the implementation is known good.

---

## Genesis text storage — CONFIRMED

### Text is plain ASCII, not 6-bit packed

A significant departure from the DOS games. The DOS engine packs four
6-bit characters into three bytes; the Genesis port stores NUL-terminated
ASCII directly. Text extraction on the Genesis side is therefore trivial.

### String tables are self-describing

The engine stores text as a table of 16-bit big-endian offsets, each
self-relative to the table's own base, immediately followed by the string
data it indexes. That makes `entry[0]` equal to the table length in bytes,
which is a reliable signature for finding these tables.

Offsets are **not** monotonic — the engine deduplicates and shares strings,
so tables routinely point backwards into text they have already indexed.
(An earlier version of the scanner required monotonicity and found only one
table as a result.)

`tools/find_text.py` scans for them. The ROM contains only two:

| address | entries | contents |
|---|---|---|
| `0x0446E` | 94 | ECL opcode mnemonics |
| `0x11DC4` | 393 | item names — `knife`, `mono`, `cutlass`, `sword`, `d.r. x-bow` |

**The campaign dialogue is not in a global ROM table.** That is consistent
with the argument encoding: ECL string arguments are offsets added to the
ECL base pointer at `$FFB9A4`, so text lives inside each loaded ECL
resource, not in a shared pool.

---

## The Genesis ECL resource directory — CONFIRMED

The loader at `0x040CE` resolves an ECL block by id:

```
040D4: 41 f9 00 03 8c e6   lea     $38CE6,a0       ; id list
040DA: 12 18               move.b  (a0)+,d1        ; next id
040DC: 6a 1a               bpl.s   $040F8          ; 0xFF terminates
040DE: 41 f9 00 00 40 ea   lea     $040EA,a0       ; "cant load ecl"
040F8: b0 01               cmp.b   d1,d0           ; requested id?
040FA: 67 04               beq.s   $04100
040FC: 58 82               addq.l  #4,d2           ; else advance index by 4
040FE: 60 da               bra.s   $040DA
04100: 20 79 00 03 8c e2   movea.l ($38CE2),a0     ; -> offset table
04106: d1 f0 20 00         adda.l  (a0,d2.w),a0    ; a0 = block data
0410A: 61 00 5d 6a         bsr     $09E76
0410E: 20 3c ff ff 6a f6   move.l  #$FFFF6AF6,d0   ; destination
04114: 32 3c 2c 00         move.w  #$2C00,d1       ; 11264 bytes
04118: 61 00 5d be         bsr     $09ED8
0411C: 21 c0 b9 a4         move.l  d0,($FFB9A4).w  ; ECL base pointer
04120: 20 79 00 04 2b 0a   movea.l ($42B0A),a0     ; SECOND directory
04126: d1 f0 20 00         adda.l  (a0,d2.w),a0
0412A: 61 00 5d 4a         bsr     ...
```

### Structure

| address | contents |
|---|---|
| `0x38CE6` | id list, one byte per block, `0xFF` terminated — **27 blocks** |
| `0x38CE2` | pointer to the stream-1 offset table (`0x38D02`) |
| `0x38D02` | 27 big-endian 32-bit offsets, self-relative to `0x38D02` |
| `0x42B0A` | pointer to the stream-2 offset table (`0x42B2A`) |
| `0x42B2A` | 27 big-endian 32-bit offsets, self-relative to `0x42B2A` |

Block ids: `00 01 03 10 11 20 21 22 23 30 31 32 34 40 41 42 43 50 51 52 53
5E 5F 60 61 62 63`. The high nibble groups blocks by region, the same
scheme the DOS games use.

Self-validating: `offsets[0]` is `0x6C` in both tables, exactly `27 * 4` —
the size of the offset table itself, so block data begins immediately after.

### Two parallel streams, both compressed

**Stream 1 is ECL bytecode.** Every block begins `01 00` followed by
high-entropy data, and block sizes (210–1427 bytes) are far smaller than
the multi-kilobyte scripts they must contain.

**Stream 2 is the text pool.** Block 0 begins with readable ASCII
(`DO YOU WANT T`) before turning to high-entropy data.

Both are decompressed into RAM at load time, which explains the
`"compression overflow"` string at `0x220C`. The 11264-byte size constant
at `0x04114` is presumably the decompression buffer.

**Next: the decompressor, reachable via `bsr $09E76` and `bsr $09ED8`.**
Cracking it opens every Genesis script and every line of Genesis dialogue,
and gives us the compressor we will need to write blocks back.

---

## Genesis ECL compression cracked — ALL 27 BLOCKS EXTRACTED

Both resource streams are LZW compressed with a variable-width code and an
unusual disambiguation scheme. Transcribed from `0x09ED8` (main loop) and
`0x0A092` (code reader).

### The algorithm

State after a CLEAR: `width` 9, `next` 0x102, `max` 0x1FF, `thresh` 2.

Codes are read MSB-first into a 32-bit accumulator. Each read takes the top
`width - 1` bits as a candidate:

- if that value is **greater than `thresh`** it is unambiguously a literal,
  and only `width - 1` bits are consumed;
- otherwise one more bit is consumed and, if set, `0x100` is added.

`thresh` is exactly the count of dictionary entries allocated beyond 256 —
precisely the range where a literal and a dictionary code could collide. So
the extra bit is spent only when it is actually needed. Neat, and it is why
naive fixed-width LZW decoders fail on this data after ~10 bytes.

Adding an entry increments both `next` and `thresh`. When `next` reaches
`max`, `width` grows (ceiling 12), `max` becomes `(1 << width) - 1`, and
`thresh` is reset to `0xFFFF` — forcing full-width reads until it catches up.

One further detail: the ROM branches on `code >= next` (`bcs` at `0x09F5A`),
not on equality, routing anything at or past the dictionary frontier through
the KwKwK path. One text block (id `0x61`) genuinely needs this.

### Results

`tools/genesis_ecl.py` extracts everything:

- **27 blocks**, both streams, every one terminating on a clean END code
- **61,173 bytes of ECL bytecode**
- **110,088 bytes of text, 100% printable ASCII**

Sample from text block `0x11`:

```
A NEO OFFICER GREETS YOU.
'I AM CARLTON TURABIAN. WELCOME TO SALVATION III. WHEN YOU ARE READY,
 COME SEE ME AT HEADQUARTERS FOR YOUR FIRST ASSIGNMENT.'
'RAM HAS KIDNAPPED THE DESERT RUNNER ATHA. THEY THREATEN TO KILL HER
 IF YOU DON'T TRAVEL TO JUNO.'
```

**The entire Genesis campaign script is now readable.**

### Structural confirmation

ECL is loaded to `$FFFF6AF6` (the destination constant at `0x0410E`), so
the Genesis code base is `0x6AF6`. Every decompressed block opens with five
`GOTO` instructions — the event hooks — and in every one `onInit` targets
`0x6B0A`, which is offset `0x14`.

The DOS blocks are identical in shape: base `0x8000`, `onInit` at offset
`0x14`, and `onRest`/`onRestInterruption` pointing to the same handler.

That is independent confirmation that the Genesis port kept the DOS ECL
block layout wholesale, and it validates the decompressor: a wrong decoder
would not produce five well-formed `GOTO`s with a consistent `onInit`
offset across 27 blocks.

---

## Genesis ECL disassembly — WORKING, but argument counts limit coverage

`tools/genesis_disasm.py` walks the extracted bytecode from the five event
hooks, follows jump targets, and resolves string arguments against the
block's companion text resource.

Sample from block `0x60` (56.5% reached):

```
00000  GOTO             [0x6B54]        ; onMove
00004  GOTO             [0x6C22]        ; onSearchLocation
00008  GOTO             [0x6B53]        ; onRest
0000C  GOTO             [0x6B53]        ; onRestInterruption
00010  GOTO             [0x6B0A]        ; onInit
00014  SOUND            0x32
00017  SAVE             0x60, [0x9BCB]
00029  COMPARE          [0x97E8], 0x60
0002F  IFEQ
0005E  AND              [0x9AF9], 0x3F, [0x9E6F]
00067  COMPAREAND       [0x9E6F], 0x26, [0x9AFA], 0x1
0013B  ONGOTO           [0x9E6F], 0x2A, [0x6CB5], [0x72E6], ... (42 targets)
001C8  COMPARE          [0x9800], 0x14
001EB  IFNE
001EC  GOTO             [0x6CEC]
```

That is unambiguously correct: a 42-entry jump table whose count matches its
`0x2A` argument, sane flag addresses clustered at `0x97xx`/`0x9Axx`, and a
correctly structured event-hook header.

### Coverage is 19.6%, and the cause is known

Blocks range from 1.4% to 56.5%. The limiting factor is the nine opcodes
whose argument counts are still uncertain — a single wrong count desyncs the
instruction stream for the rest of that run, so the walk terminates early.

This is not a format problem. The format is understood. It is a
data-gathering problem, and the fix is a live instruction trace: consecutive
values of `a2` (the ECL program counter) at the fetch in `0x03346` give
exact instruction sizes, hence exact argument counts.

### Open question: string argument base

In block `0x60`, a `PRINTCLEAR` resolved to text starting 68 bytes into a
string rather than at its start. Two candidate explanations, not yet
distinguished:

1. the walk desynced at that site and the string offset is simply garbage
   (the instruction was reached by a jump, not by fall-through), or
2. string arguments are not raw byte offsets into the text resource.

The first is more likely given the surrounding instructions decode cleanly
and the site was jump-reached. Resolve it once argument counts are solid.

---

## Save system — RESOLVED: undeclared 8 KB SRAM

The ROM header declares no external RAM (the field at `0x1B0` is blank), but
the game does use battery-backed SRAM. Running it under BlastEm produces:

```
Saved SRAM to ~/.local/share/blastem/countdown/save.sram
```

an 8192-byte file beginning `00 00 12 34 03 03 03 00`.

### Evidence in the ROM

SRAM is mapped at the standard Genesis location, `0x200000`. Nine direct
references exist, e.g.:

| ROM offset | target |
|---|---|
| `0x01246` | `lea $200000,a0` |
| `0x0196E` | `lea $200011,a3` |
| `0x0230A` | `lea $200009,a0` |
| `0x03B3A` | `lea $200001,a0` |
| `0x07DF4` | `move.l #...,$200017` |
| `0x1716A`, `0x176E8`, `0x19208` | `move.l #...,$20001A` |

The save-validity check sits at `0x19D5C`:

```
19D56: 10 18                move.b  (a0)+,d0
19D58: 51 c9 ff f8          dbra    d1,$19D52
19D5C: b0 bc 12 34 56 78    cmpi.l  #$12345678,d0
19D62: 66 c2                bne.s   ...
```

**The save signature is `0x12345678`.** A save whose magic does not match is
rejected, which is the mechanism to mimic or extend for a port.

### Why this matters

"Stable saves" is a stated project goal and the blank header field made the
mechanism an open question. It is now answered: the port needs 8 KB of SRAM,
and a patched build must either declare it in the header (`RA` at `0x1B0`)
or continue relying on emulators and flashcarts tolerating the omission.
Declaring it is the safer choice for real hardware.

---

## Live trace validation — the disassembler is correct

A breakpoint at the ECL opcode fetch (`0x03346`) with BlastEm's
`di/x a2` produces the script program counter on every instruction. The
differences between consecutive values are exact instruction sizes.

### The running block is id 0x10

Matching observed instruction boundaries against all 27 extracted blocks
identifies block `0x10` uniquely — six independent boundaries all agree.
That simultaneously validates the LZW decompressor (RAM contents match our
decompressed output) and the code base of `0x6AF6`.

### Results: 16 of 16 consecutive pairs match

```
offset  expected  got  instruction
0x058      3       3   PICTURE          0x48
0x05B      4       4   PRINTCLEAR       str[0x0000]
0x06A      3       3   PICTURE          0xFF
0x06D      5       5   FOR              0x0, 0x7
0x072     10      10   GETABLE          [0x7310], [0x98EC], [0x9AFA]
0x07C      1       1   STEPFORWARD
0x07D      1       1   ENDFOR
0x07E      3       3   SOUND            0x2C
0x081      3       3   EXPLOSION        0x5
0x084      1       1   DELAY
0x085      3       3   EXPLOSION        0x1
0x088      1       1   DELAY
0x089      3       3   EXPLOSION        0x2
0x08C      1       1   DELAY
0x08D      3       3   EXPLOSION        0x6
0x090      5       5   VIEW             0x1, 0x78
```

The one apparent mismatch (`0x05F`, expected 11) spans a gap in the capture
where the trace display was not active, so those two samples are not
consecutive instructions.

This confirms argument counts for `PICTURE`, `PRINTCLEAR`, `FOR`,
`GETABLE`, `STEPFORWARD`, `ENDFOR`, `SOUND`, `EXPLOSION`, `DELAY` and
`VIEW`. `FOR` was previously uncertain and is now confirmed at 2.

It also reads as real code: a `FOR` loop wrapping `GETABLE`/`STEPFORWARD`,
then a sequence of `EXPLOSION`/`DELAY` pairs — an animated explosion.

### Argument type 0x80 is a string OFFSET, not an inline string — CONFIRMED

The trace measured `12 80 00 00` (`PRINTCLEAR`) at **4 bytes**. Under the
DOS interpretation, type `0x80` is an inline packed string introduced by a
length byte, which would have made it 3.

On the Genesis, type `0x80` takes the ordinary 2-byte payload and that value
is a string offset — exactly matching the argument fetcher at `0x0404A`,
which adds type-`0x80` values to the ECL base at `$FFB9A4`.

This was the cause of the earlier "string resolved 68 bytes into the text"
anomaly: every string argument was being mis-sized, desyncing the stream
after it. `str[0x0000]` in block `0x10` resolves correctly to the opening
narration.

**Both DOS string forms therefore need conversion for a port**: the DOS
engine's inline 6-bit packed text must be lifted into a separate pool and
rewritten as 2-byte offsets. That is the string half of the translation
problem, now precisely specified.

---

## BLOCKER: the ROM refuses to run if a single byte is changed

Found by boot-testing a rebuilt ROM. This blocks the patch-the-cartridge
approach until the mechanism is understood.

### Measuring this correctly

Screen capture proved unreliable and produced contradictory results -- the
intro contains genuine black frames, windows move between runs, and other
windows can occlude the capture region. Two different sampling rates gave
two different answers for the same ROM.

The sound method is BlastEm's `-l` flag, which logs every distinct 68000
address executed to `address.log`. It is fully deterministic: repeated runs
of the same ROM give identical counts.

```
tools/... or:  blastem -l rom.gen ; sort -u address.log | wc -l
```

| ROM | change | 25s | 60s |
|---|---|---|---|
| `countdown.gen` | none | 985 | 986 |
| `countdown_copy.gen` | byte-identical, new filename | 983 | — |
| `countdown_rebuilt.gen` | all ECL streams recompressed | 947 | — |
| `countdown_hello.gen` | rebuild + one edited string | 947 | 947 |
| `countdown_late.gen` | **one byte** flipped in block 0x63's text | 947 | — |

The counts are stable from 25s to 60s, so the modified ROMs are genuinely
stuck rather than merely slower.

### The decisive case

`countdown_late.gen` flips a single byte 500 bytes into the compressed text
of ECL block `0x63` -- the last block, a late-game area the boot sequence
never loads. It stalls identically. Boot cannot be reading that data, so
this is an integrity check over the ROM image rather than resource
corruption.

(An earlier version of this note cited a byte flipped in "unused padding" at
`0xF2000`. That evidence was weak: the region past `0xF1FD8` contains a long
`0xFF` run but is not uniformly unused, so corruption could not be ruled
out. The block `0x63` case replaces it.)

### Where it stalls

All ROMs execute an identical first 947 addresses; the working one then
reaches 36 more, in the decompression code around `0x2328`-`0x2850` and at
`0xDE8C`-`0xDFEC`. So the modified ROMs never get as far as decompressing
their resources.

The stall region disassembles (Capstone, m68k) as an SRAM surface test
followed by a hang loop:

```
19CEC  move.w  #$1FFF,d2          ; 8192 words
19CF0  move.w  #$1,d1
19CF4  move.w  #$7,d0             ; walk 8 bits
19CF8  move.w  d1,(a0)            ; write pattern to SRAM
19CFA  cmp.b   $1(a0),d1          ; read back (bus odd -> byte at +1)
19CFE  bne.b   $19D26             ; mismatch -> hang
19D02  dbra    d0,$19CF8
19D08  dbra    d2,$19CF0
19D0C  movea.l #$200000,a0
19D12  move.l  #$120034,(a0)+     ; write the 0x12345678 signature,
19D18  move.l  #$560078,(a0)+     ;   interleaved for the odd bus

19D26  move.w  d3,d0              ; <-- hang loop
19D28  move.l  #$C0000000,$C00004 ; CRAM write address 0
19D36  move.w  d1,$C00000         ; write a colour
19D44  tst.b   $B4C2.w
19D48  beq.b   $19D44             ; wait for vblank
19D4A  sub.w   d4,d0              ; fade
19D4C  bra.b   $19D28             ; forever
```

That loop is the black screen: it fades the palette and never exits. Several
failure paths branch into it, so reaching `0x19D26` is the engine's generic
"give up" state rather than proof that the SRAM test specifically failed.

### Still unknown

What computes the verdict. Ruled out so far:

- **The header checksum.** Variants carrying correctly recomputed values at
  `0x18E` still fail (stored == computed, verified), and the standard Sega
  checksum loop (`add.w (a0)+,dN` before a `dbra`) does not appear anywhere.
- **A stored constant.** Nine candidate whole-ROM aggregates (byte/word/long
  sums and XORs, several ranges) were computed and searched for in the ROM;
  every hit landed in high-entropy compressed data.
- **Emulator configuration.** BlastEm keys its database off product ID
  `T-50286`, which every variant preserves; failing ROMs log the same
  database match and SRAM mapping.

Next step is to find which branch leads to `0x19D26` on a modified ROM. With
Capstone now available, the practical approach is to enumerate every branch
targeting `0x19D26`, then use BlastEm's debugger to see which one is taken.

### Consequences

The rest of the pipeline is verified sound -- the compressor reproduces
SSI's output byte-for-byte on 51 of 54 streams, the identity rebuild is
byte-perfect, and rebuilt resources decompress to the original bytes. The
tooling is correct; the cartridge simply will not accept modified content
yet.

This strengthens the case for reimplementing the engine rather than patching
the original, which never has to satisfy whatever this check is.

---

## The cartridge can be expanded to 2 MB — CONFIRMED

The anti-tamper sum at `0x0FFFB0` iterates `0x3FFEC` longwords, which is
`0xFFFB0` bytes: **the first megabyte only.** Anything placed above that is
never summed.

BlastEm's ROM database maps the cartridge generously:

```
T-50286 {
    map {
        0        { device ROM  last 1FFFFF }    <- 2 MB of ROM space
        200000   { device SRAM last 3FFFFF }
    }
}
```

So `0x100000`-`0x1FFFFF` is addressable, unchecked, and unused.

### Verified

`roms/countdown_2mb.gen` is a 2 MB image with the GEO stream relocated to
`0x100000`, the loader retargeted, and the header's ROM-end field at `0x1A4`
updated to `0x1FFFFF`. It boots to **985 distinct executed addresses — the
stock ROM's exact count.**

### Why this matters

Matrix Cubed's transpiled content needs 159,374 compressed bytes against the
99,289 that Countdown's resources occupy — **1.61x**. That was the strongest
remaining argument that the original cartridge could not host the game.

It can. Doubling the ROM yields roughly 1 MB of free space, six times what
the shortfall requires, and the checksum does not object because it never
looks there. Growing further to 4 MB needs only a database entry for an
emulator, and nothing at all on a flash cart.

The relocation technique is the same one already used for the GEO stream:
write the resource into new space and retarget the loader's pointer.

---

## The resource directory is additive, not fixed-size — CONFIRMED

Both loaders walk their id list dynamically, so a **longer list is simply
found**. Nothing in the engine is sized for the 27 areas Countdown shipped.

**ECL**, at `0x040CE`: `move.b (a0)+,d1 / bpl.s` walks to the `0xFF`
terminator, adding 4 to the offset-table index on each miss. No count.

**GEO**, at `0x5766`:

```
0576A: link.w  a6, #$ffde        ; 34 bytes of locals
0577E: bsr.w   $9ed8             ; decompress the 2-byte count to -2(a6)
0578A: bsr.w   $9ed8             ; decompress `count` ids to -0x22(a6)
0579E: bsr.w   $9ed8             ; then 1024 bytes per area until the id matches
057AC: cmp.w   -$2(a6), d3       ; loop bound is the count, not a constant
```

The id list is read into a stack buffer spanning `-0x22(a6)` to `-2(a6)`,
so **the engine caps at 32 map areas.** That is the only hard ceiling
found. Matrix Cubed needs 23 of them.

### Where the longer id list goes

The id list at `0x38CE6` is immediately followed by the stream-1 offset
table at `0x38D02` — but that table is dead once `tools/expand.py`
relocates both streams above 1 MB and repoints `0x38CE2`. The freed 108
bytes are enough for far more ids than the engine's geo buffer allows.
Nothing else in the ROM references that region.

## `LOADFILES` names a map, `LOADPIECES` names a wall set — CONFIRMED

In stock Countdown the set of `LOADFILES` immediates is *exactly* the set
of geo area ids, which identifies the argument.

`LOADPIECES` divides its argument by three to index a table of word
offsets at `0x51836`:

```
158C4: divu.w  #$3, d0
158CC: asl.w   #$1, d0
158CE: lea.l   $51836.l, a0
158D4: adda.w  (a0, d0.w), a0
```

which is why the debug prompt reads `Enter wallset as decimal (1,4,7..)`.
Countdown's ids 1..28 step by three across ten sets. Matrix Cubed's ids
(3, 5, 9, 11, 15, 17, ...) all fold into that range, so transplanted areas
draw **correct geometry with Countdown's wall art** rather than failing.
Porting `WALLDEF1.DAX` into this table is an art task, not an engine one.

## The engine has four entry areas, not one — CONFIRMED

At `0x04146`, before the ECL loader is called:

```
04146: tst.b   $ba5a.w
0414A: beq.b   $4154
0414C:   move.b #$3, $b9f0.w      ; -> area 0x03
04152:   bra.b  $416e
04154: tst.b   $ca21.w
04158: bne.b   $4160
0415A:   clr.b  $b9f0.w           ; -> area 0x00
0415E:   bra.b  $416e
04160:   move.b #$10, $b9f0.w     ; -> area 0x10   "load default team"
04166:   bra.b  $416e
04168: move.b  $97e8.w, $b9f0.w   ; -> the saved area, on a restore
0416E: moveq   #$0, d0
04170: move.b  $b9f0.w, d0
04174: bsr.w   $40d0
```

Which one runs depends on `0xBA5A` and `0xCA21`, set by the start-up menu.
**Choosing "load default team" enters at area `0x10`,** so a boot change
made only in area `0x00` is never executed — which is exactly what a play
session showed: a marker string printed by a stub in `0x00` never appeared,
while the game went straight to the space hub, because Matrix Cubed's area
`0x10` is a 30-byte entry stub whose whole body is `NEWECL 0x13`.

Correction to an earlier note: the ECL loader begins at `0x040D0`. `0x040CE`
is the `rts` of the routine above it. Searching for callers of `0x040CE`
found none and made the loader look unreachable.

## The art resource directory — CONFIRMED, and relocatable

Found by walking back from the `"loadpieces error 1"` site. The loader at
`0x09BB6` has three callers, and one of them resolves a resource by id
against a table:

```
099C6: lea.l    $9a14.l, a1      ; the directory
099CC: move.b   $4(a1), d1       ; this record's id
099D0: bmi.b    $99f6            ; a negative id ends the table
099D2: cmp.b    d0, d1
099D6: addq.l   #$8, a1          ; 8-byte records
099DE: movea.l  (a1), a0         ; -> the resource
099DA: move.b   $5(a1), d3       ; chunk size
```

Records are `{pointer:4, id:1, chunk:1, flags:2}`. The table at `0x09A14`
holds **52 records, ids 0x00–0x40**, pointing into `0x075E10`–`0x08C886`,
and ends at `0x09BB4` — immediately followed by the loader's own entry
(`4E56 F7EC`, `link a6, #$f7ec`). **So it cannot grow in place.**

It can be relocated, which is the same move already used for the ECL and
GEO streams: the address is a single absolute operand at `0x099C8`, so
pointing it at a longer table in expanded ROM makes the directory additive.

A second table of 4-byte pointers sits at `0x0998C`, reached from the other
caller at `0x09982`, indexing `0x066116` onward.

### What still blocks injection

The converted art is in `.gart`, a container written for this project. The
engine wants its own layout, compressed with the SSI codec at `0x09ED8`
and read in `chunk`-sized pieces. The codec is already solved — 
`tools/lzw_encode.py` reproduces SSI's output byte-for-byte on 53 of 54
ECL streams — but the uncompressed picture layout has not been reversed
yet. That, not space or directory structure, is the remaining work.

### Default pictures per area

`0x082EC` picks a backdrop when no picture is set: a table of `area, picture`
pairs at `0x08336` (17 entries, `0xFF` terminated), falling back to
`0x08330` indexed by `0x979B`. Matrix Cubed's new areas are absent from it
and take the fallback, which is harmless — every id in it is one Countdown
has.

### The picture container — CONFIRMED

Resources the directories point at decompress with the ECL/GEO codec and
then have this shape:

```
 0  2  unique tile count
 2  2  nametable size in BYTES
 4  2  flags (0 in all 248 found)
 6  .. nametable, one big-endian word per cell, tile index in bits 0-10
 .. .. tile data, 32 bytes each, VDP 4bpp, high nibble = left pixel
```

Self-validating: length is exactly `6 + nametable_bytes + 32 * tiles` for
every resource, which makes a blind scan of the ROM safe. `tools/genesis_pic.py`
does that scan and finds **248 pictures**, dumping each as a PNG.

Width comes from the directory record's `chunk` byte, in tiles. Shapes by
nametable size:

| entries | count | shape |
|---|---|---|
| 9 | 110 | 3x3 tiles, 24x24 — icons |
| 162 | 57 | 18x9 tiles, 144x72 — combat figure sheets |
| 264 | 10 | 11 tiles tall, 88 px — the picture-window height |
| 232, 270, 437, … | 10 each | various |

The 162-entry family renders as rows of small character frames, confirming
it is the figure art the `ADDFIGURE` callers use rather than backdrops.

**Not yet found: the 88x88 portrait directory.** The picture loader sets up
an 88x88 region (`moveq #$57` twice at `0x04E20`), which would be 11x11
tiles and 242 nametable bytes, and no resource has that size. The portraits
reach the screen by some other arrangement.

### The table at 0xF14F2 is the ITEM AND UI ICON table — CORRECTED

Found by clustering: every ROM location holding a pointer to one of the 248
decodable pictures, grouped by constant stride. Four directories fall out:

| address | entries | stride | contents |
|---|---|---|---|
| `0x0998C` | 12 | 4 | 18x9 figure sheets |
| `0x09A14` | 52 | 8 | combat figures, `{ptr, id, chunk, flags}` |
| `0xF14F2` | **110** | 4 | **the `PICTURE` table** — 3x3 tiles, 24x24 |
| `0xF170E` | 50 | 4 | wall and dungeon pieces |

**This was wrong.** `0xF14F2` is not indexed by the `PICTURE` operand at
all. Its only two consumers are engine code:

```
0A794: move.b (a3)+, d0 / cmp.b #$ff / lea $f14f2   ; batch list, 0xFF-terminated
10AC4: add.b  d1, d0     / lea $f14f2               ; item/equipment lookup
```

It is the **item and UI icon table**. It was mistaken for the picture
directory because its 110 entries happen to match the `PICTURE` id range —
a coincidence that was never checked. Writing artwork into it replaces the
inventory and equipment icons, which is exactly what a play session saw.

All 110 entries do decode as pictures, so **icon ids 0–109 are valid**, and
the `artmap.py` bound derived from that still holds. Rendering the ones Countdown's scripts
use gives a padlock, an eye, a wrench, a gender symbol, faces, a heart, a
crosshair, crossed swords, a medical cross and a rocket — the icons that
appear in the window beside the text.

This corrects the guard in `tools/artmap.py`, which had allowed only the 33
ids Countdown's scripts happen to reference and was therefore blanking 183
uses of art that resolves perfectly well. Exactly one Matrix Cubed
`PICTURE` id is genuinely out of range: `0x6F` (111).

The Genesis port shows 24x24 icons where DOS shows 88x88 portraits, so
injecting Matrix Cubed's art here means reducing its portraits to the
icon slot the port designed for, not pasting them in at source size.

### `"loadpieces error 1"` is a FIGURE miss, not a picture miss

The error at `0x09CF6` is raised from the chunked decompressor at `0x09BB6`,
which has exactly three callers — `0x09982`, `0x099EC` and `0x158A0`. None
of them is the picture path, which runs `0x08516` → `0x08562` → `0x095BE`.
So no `PICTURE` operand can ever produce this error, and hours were spent
guarding the wrong opcode.

The resource id is dispatched at `0x099BC`:

```
099BC: bclr.b #$7, d0      ; bit 7 set?
099C0: bne.b  $9964        ; yes -> a 12-entry table at 0x0998C, NO bounds check
099C6: lea.l  $9a14.l, a1  ; no  -> search the figure directory by id
099D0: bmi.b  $99f6        ; ran off the end: not found
```

A miss is not ignored. `0x099F6` loads a pointer that was never a resource,
the decompressor reads nonsense, its remaining-bytes counter goes negative,
and the game stops.

The figure directory holds 52 ids. Matrix Cubed's `LOAD_MON` and
`SPRITE_START` name ten it does not have — `0x2E`–`0x36` and `0x3F` — across
**237 references**. `tools/artmap.py` substitutes the nearest lower id,
which keeps the encounter with another creature's sprite rather than
dropping the fight.

### Palette lines — CONFIRMED

Read straight off the art, from bits 13-14 of every nametable entry:

| art class | palette line |
|---|---|
| `PICTURE` icons | **0** (921 cells), a little line 1 (69) |
| wall and dungeon pieces | **2** (8089 cells), some line 0 (1371) |
| figure sheets | 0 |
| combat figures | 0 |

Pictures and walls are on **different lines**, and **line 3 is unused** by
any of the 248 picture-container resources.

All four lines are uploaded together, from one RAM buffer:

```
0A490: move.l  #$c0000000, (a4)    ; CRAM from address 0
0A496: moveq   #$3f, d7            ; 64 words = 4 lines
0A498: lea.l   $ffff0240.l, a1
0A49E: move.w  (a1)+, (a5)
```

so line 3 lives at `0xFFFF02A0`. Nothing in the ROM writes that address
directly; the buffer is filled wholesale, and `0x0A160` reads CRAM back
into it rather than writing it, which is a fade rather than a load.

### The palette is what limits injected art, not the icon size

Measured on six portraits, mean per-pixel error:

| | error |
|---|---|
| engine palette, 24x24 | **65.1** |
| the image's own 16 colours, 24x24 | **20.9** |
| the image's own 16 colours, 88x88 | 16.2 |

Dropping from 88x88 to 24x24 costs about 5. Losing control of the palette
costs about 44. So the icon slot is not the problem — colour is.

It also exposed a likely mistake in `tools/inject_pic.py`: it quantises
against the palette at `0xF16AA`, which `LOADPIECES` selects with its id
divided by three. That is the **wall** palette, and walls are on line 2
while icons are on line 0.

## The real ECL picture path — CONFIRMED

Followed from the opcode rather than guessed: `PICTURE` (`0x03662`) stores
its id at `0xB525`, `0x04DFA` sets up an 88x88 region, `0x08516` dispatches,
and two loaders resolve the id:

```
0B766: lea $51302, a0      ; id list, negative-terminated
0B76C: lea $5130a, a1      ; 32-bit pointers
0B778: cmp.b d3, d0        ; match the id
0B780: movea.l (a1), a0    ; -> the picture
```

and `0x0B7B4` the same shape against `0x51326` / `0x51360`. The string
`"LoadBigPic failed"` at `0x0B7A2` sits inside the first.

| directory | ids | contents |
|---|---|---|
| `0x51302` / `0x5130A` | `0x70`–`0x78` | `VIEW` big pictures, 288x120 |
| `0x51326` / `0x51360` | `0x20`–`0x6F`, 57 entries | `PICTURE` portraits, 88x88 |

**`0xF14F2` is not this.** It is the item and UI icon table, and writing
artwork into it replaces inventory icons — see the correction above.

### The container carries its own palette

```
 0  2  unique tile count
 2  2  nametable size in bytes
 4  2  flags -- bit 3 means a palette follows the nametable
 6  .. nametable, tile index in bits 0-10, palette line in bits 13-14
 .. 32 sixteen CRAM words, when flags bit 3 is set
 .. .. tile data, 32 bytes each
```

Self-validating as before: length is exactly
`6 + nametable + (32 if flags & 8) + 32 * tiles`.

Portraits are **six frames of 11x11 tiles** — 726 cells is 6 x 121 — and
render as an animation: a RAM warrior raising and firing a rifle. Big
pictures are 36x15 tiles at 288x120.

**This is the right target for Matrix Cubed's art, and the dimensions
already match.** The DOS portraits recovered by `gbimage_vd.py` are 88x88
with multiple frames, and `BIGPIC1` is 304x120 against the Genesis 288x120.
Because the palette travels with the image, injected art is not stuck with
whatever the area has loaded — the measured gap between an image's own
sixteen colours and a borrowed palette was 21 against 63.

## The intro and attract sequence — CONFIRMED

The intro is a routine at `0x012FC`, not a directory. It plays a music track
and loads screens by absolute address:

```
01304: move.w #$2e, d0
01308: jsr    $1b900.l      ; title music, track 0x2E
01338: lea.l  $99b5f.l, a0  ; SSI "presents", 320x224, flags 0x0004
013A8: lea.l  $96d4a.l, a0  ; the scene behind the titles, 320x200
013B8: lea.l  $9ab8b.l      ; and six overlays stamped on top
013C8: lea.l  $9acf7.l
0144E: lea.l  $9ae4d.l
0148E: lea.l  $962d9.l      ; Earth
0151A: lea.l  $9b0b9.l
```

Each screen is named by a `lea` operand, so replacing one needs no table to
grow — which is why `tools/inject_title.py` is safe where expanding the
picture directory was not.

### The palette flag selects a CRAM line

Bit 2 means the embedded palette loads into **line 2**, bit 3 into **line
3**, and the nametable must ask for the same line in bits 13-14. Getting
this wrong is not subtle: the injected title drew in blues and pinks because
its palette went to line 2 while its cells asked for line 0. The stock
screens confirm it — `0x99B5F` has flags `0x0004` and every one of its 1120
cells selects line 2.

### The attract demo is an ECL area

Leaving the title alone long enough reaches a gameplay view with a portrait
and narration. That is **area `0x03`**, reached from the entry dispatch when
`0xBA5A` is set, and it is an ordinary script:

```
0014: SOUND      0x2E
0023: LOADFILES  0x3, 0x7F, 0xFF
003F: NEWREGION  0x0, 0x1, 0x0, 0x0, 0x3, 0x4
0060: PICTURE    0x48
0063: PRINTCLEAR "THE ONCE-PROUD EARTH HAS BEEN REDUCED TO DESOLATE RUINS..."
0067: DELAY  (x6)
006D: PICTURE    0x3E
0070: PRINTCLEAR "BUCK ROGER'S TIRELESS EFFORTS FOR THE NEW EARTH ORGANIZATION..."
0079: STEPBACK / STEPFORWARD      ; the party walking in the map window
```

Ten narration panels, each a picture, a line of text and a delay, with the
party stepped around the map between them. Being a script, it is as
replaceable as any other area.

**Matrix Cubed has no attract demo to port.** Searching all 33 of its ECL
blocks for the narration's distinctive phrases finds nothing: the sequence
is a Genesis-port addition, and DOS Matrix Cubed has no equivalent. Giving
it a Matrix Cubed intro would mean writing one, which is authoring rather
than porting, and is a decision worth making deliberately.

## The sound driver — CONFIRMED custom, not SMPS or GEMS

Music does not run on the 68000. The routine at `0x1B89A` hands a track
pointer to the Z80:

```
1B8BC: movea.l #$a00000, a1     ; Z80 address space
1B8D6: move.b  d1, $c(a1)       ; command byte
1B8DC: movea.l #$a0003a, a2     ; track pointer
1B8E6: bsr.w   $1b6c8
```

and `0x1B5CE` uploads the driver itself: **6112 bytes of Z80 code at ROM
`0x19D86`**, copied to `0xA00000`.

It is not one of the drivers the community has tools for. The blob carries
its author's signature in plain text — **`SHayes1991`** — and its track
headers match neither SMPS nor GEMS:

```
0x29E9E: 2a f8 0d 36 7c 00 88 88 ...
0x2BEC4: 2a f8 0d c6 7b 00 88 88 ...
0x2CC8E: 2a f8 0c b6 7a 00 88 88 ...
```

Every track opens `2A F8`, then a varying word, then a byte in `0x7A`-`0x7D`,
then `00`, then event data dominated by values around `0x86`-`0x8C`. The
dispatcher at `0x1B900` indexes a kind table at `0x1B9D4` (76 entries) and
pointer tables at `0x1BA20` and `0x1BAF4`.

### What this means for putting Matrix Cubed's music in

DOS Matrix Cubed's music is XMI — MIDI events for AdLib and MT-32. The
Genesis needs YM2612 register writes in *this* driver's format. Recording
the DOS audio instead does not help: the Genesis has one 8-bit PCM channel
and nothing like the bandwidth for a streamed song.

So the work is: disassemble 6112 bytes of Z80, find the sequence
interpreter, document the event encoding, then write an XMI-to-SSI
converter. Bounded, but days rather than hours, and none of the existing
MIDI-to-Genesis tools apply because they target SMPS or GEMS.

The alternative is to replace the driver wholesale with one that has
tooling, and retarget the 68000's calls. That trades reversing an unknown
format for porting a known one, and would change every sound effect too.

### The driver's sequence language is MIDI-shaped — CONFIRMED

Disassembled with `tools/z80dump.py` (`pip install z80dis`). The dispatch at
Z80 `0x087D` switches on the **top nibble** of a status byte and takes the
channel from the low nibble:

```
087D: LD B,A
087E: AND 0xF0
0880: CP 0x80    ->  note off
089F: CP 0x90    ->  note on
08AE: CP 0xC0    ->  program change
08C7: CP 0xF0 / CP 0xFC  ->  end of track
088E: AND 15     ->  channel
08F2: JP 0x08F2  ->  anything else hangs the driver
```

Running status is the MIDI convention exactly — a byte with bit 7 clear
reuses the previous status:

```
0960: LD A,(IY)
0964: JP m,0x096c     ; bit 7 set: this is a new status byte
0967: LD A,(0x00E7)   ; otherwise reuse the last one
0973: LD (0x00E7),A
```

and every handler returns through `0x0914`, which reads **one delta byte**
into the tick countdown at `0x00E8`. Channel 9 is percussion, keyed by
**General MIDI note numbers** — `0x24` bass drum, `0x26` snare, `0x31`
crash, `0x36` tambourine.

So an event is `status, data…, delta`, with running status, over GM
semantics. **That is very close to XMI's own encoding**, which is what makes
converting Matrix Cubed's music plausible rather than hopeless.

### What is still unknown

Where the sequence bytes live. The Z80 plays from a 1 KB ring buffer at
`0x1A00`–`0x1E00` (`0x049A` wraps `IY` back to `0x1A00` at `0x1E00`), and
the 68000 copies only a 24-byte header to `0xA0003A` before starting
playback (`0x1B8DC`). Two tables were ruled out by decoding them:

| table | holds |
|---|---|
| `0x1BA20` | **DAC samples** — data sits around `0x88`, which is near-silence in unsigned 8-bit PCM |
| `0x1BAF4` | **FM voice parameters** — short records, no status bytes |

Neither decodes as a sequence, and a track cannot begin with a running-status
byte, so the stream starts somewhere the 24-byte header points at. Finding
that is the remaining piece before an XMI converter can be written.

### The music format — SOLVED

The sequences are **not** at either table ruled out above. The dispatch at
`0x1B900` tests the kind byte: bit 7 means music, and that branch indexes a
third table:

```
1B990: andi.b #$7f, d0
1B9B2: lea.l  $1bac0.l, a0      ; the MUSIC table
1B9B8: move.l (a0, d0.w), d0
1B9BC: bsr.w  $1b64a
```

`0x1BAC0` points straight at the event stream. A track is:

```
[lead-in delta] then repeated:  [status or running status] [1 data byte] [1 delta byte]
```

| status | meaning |
|---|---|
| `0x8n` | note off, one data byte: the note |
| `0x9n` | note on, one data byte: the note |
| `0xCn` | program change, one data byte: the patch |
| `0xFC` | end of track |

Channel is the low nibble and **channel 9 is General MIDI percussion**.
There is **one** data byte per event, not MIDI's two — no velocity. The
handler at `0x088D` reads exactly one (`LD D,(IY)`, `CALL 0x049A`).

Decoding `0x0360D8` gives music rather than noise, which is the test that
matters:

```
C1 program 04      C2 program 01      C3 program 06
99 note_on 24  (percussion, GM bass drum)
91 note_on 21  A1        81 note_off 21
91 note_on 23  B1        81 note_off 23
93 note_on 42  F#4       93 note_on 47  B4
99 note_on 29  (percussion, GM floor tom)
```

A bass line on channel 1, a fifth on channel 3, and GM drums. `tools/seq2mid.py`
exports any track as a standard MIDI file for listening.

**This is what makes converting Matrix Cubed's music tractable.** XMI is
MIDI; the driver wants MIDI with a narrower encoding. The conversion is
re-timing to one-byte deltas, dropping velocity, and emitting running
status — not a translation between unrelated formats.

### Converting Matrix Cubed's music

`tools/xmi.py` parses XMI, `tools/xmi2seq.py` converts it, and
`tools/inject_music.py` repoints an entry in the music table at `0x1BAC0`.

Three things the driver forces, all measured against SSI's own tracks rather
than guessed. Decoding the title theme at `0x0360D8` gives channels 1, 2, 3
and 9, notes 31 to 76, and never more than three notes sounding at once on a
channel. Matrix Cubed's XMI uses seven channels, notes to 94 and up to six at
once, and handing the driver that produced music for a moment and then
static — it walks its frequency and voice tables off the end rather than
clamping. So the converter folds the extra melodic channels onto 1-3, folds
notes into range an octave at a time, and drops notes past the third
sounding on a channel.

Velocity is dropped because events carry one data byte, delays over 255
ticks are split with a redundant program change, and anything that is not
note on, note off or program change is discarded — the dispatch at Z80
`0x08F2` is an infinite loop, so an unexpected status hangs the machine.

**Only two slots are replaced.** Replacing all fourteen crashed the machine
about two runs in three; one slot and two slots both measure clean. Slot 2
is the intro and slot 10 the menu and team setup, which is all a player
hears before the game proper. Why fourteen breaks is not yet known — slots 0
and 1 originally share one pointer, which may be a silence marker rather
than a song.

### Matrix Cubed's own music cues never fire

Its scripts call `SOUND_EVENT` with ids `0x81`-`0x86`, and the driver's
dispatch rejects anything above `0x4B`:

```
1B904: cmp.b #$4b, d0
1B908: bhi.w $1b9ce      ; ignored
```

So every music cue in the transplanted scripts is silently dropped, and the
only music that plays is what Countdown's boot code starts. Fixing it means
mapping those six ids onto the Genesis music ids -- `0x2C`, `0x2E`-`0x36` --
in the transpiler, not in the injector.

### A track is preceded by a region end pointer

This is what made injected music silent. On the way to the Z80 the 68000
reads the longword **before** the track:

```
1B656: movea.l d0, a0
1B658: move.l  -$4(a0), $d8ee.w
```

It is the end of a contiguous music **region**, not of one song: slots 3 and
12 start at `0x354A8` and `0x35B18` and share the value `0x35BA8`, so two
tracks live in one region. For an isolated track it works out the same as
start plus length, which is what `tools/inject_music.py` writes.

The 68000 primes the Z80 rather than letting it fetch: `0x1B824` copies the
first 1024 bytes of a track straight into the ring buffer at Z80 `0x1A00`
and keeps the advanced pointer at `0xD8E2`.

**This did not make injected music work.** The pointers are right, the
sequences decode correctly, and the tracks are the right shape, and it still
misbehaves in play. What is still unaccounted for is how the 68000 refills
the ring buffer as the Z80 consumes it, and whether anything there assumes
music lives in the first megabyte -- every stock track does, and the
injected ones are at `0x190000`.

---

## Which song plays in which scene — what is proven and what is not

The question is whether Matrix Cubed's six music cues are being matched to
the right songs. Three things were tried.

**The XMI carries no cue ids.** `BUCKA.XMI` is `FORM XDIR` (`INFO` = 7
sequences) then `CAT XMID` holding seven `FORM XMID`, each just `TIMB` and
`EVNT`. Songs are selected by index; nothing in the file names a cue.

**The DOS code did not give it up.** Neither `GAME.OVR` nor `START.EXE`
contains the string `XMI`; the filename is built at runtime from a
card-indexed table of length-prefixed names at `START.EXE:0x10B19`
(`bucka`, `buckb`, `buckc`, then the `.ADV` driver names). The ECL
interpreter has no indexed jump (`jmp cs:[bx+d16]` and friends: zero hits),
and all 37 real `and al,0x7F` sites in `GAME.OVR` are character and item
record handling -- the `mul dx` by 0x22 and by 9 record strides -- not a
sound dispatch.

**What the scripts and the songs do say.** Both halves are measurable.

Scene text around each cue, from `ecl.disassemble`:

| cue | uses | what is happening |
|---|---|---|
| 0x81 | 25 | mixed; relief and arrival, but also "RATWURST ATTACK!" |
| 0x82 | 20 | ambush -- RAM forces pour in, agents flood the hall |
| 0x83 | 9 | grim -- slaughter, imprisonment, gutted sprawl |
| 0x84 | 3 | awe -- the Living Ship, "ITS IMMENSE SIZE" |
| 0x85 | 5 | villains -- "YOU ARE TOO LATE!", Lord Refuge |
| 0x86 | 2 | warm -- help in unexpected forms, Buck and Wilma |

Song character, from the note data (key by pitch-class correlation
against Krumhansl profiles):

| song | length | density | key | drums |
|---|---|---|---|---|
| 0 | 39.8s | 16.4/s | G# major | 214 |
| 1 |  7.6s | 10.3/s | A# minor | 31 |
| 2 | 11.0s | 14.0/s | A minor | 64 |
| 3 | 12.0s |  3.7/s | A# minor | 0 |
| 4 | 16.5s |  5.0/s | F minor | 2 |
| 5 | 10.5s |  7.6/s | F major | 37 |
| 6 | 21.6s | 27.6/s | E major | 191 |

Under the assumption that cue 0x8n plays song n, four of the six match
their scenes well: 0x82 ambush to the fast minor-key song 2, 0x83 grim to
the sparse drumless song 3, 0x84 awe to the slow spacious song 4, 0x86 warm
to the bright major song 6. 0x81 is the most-used cue and gets the shortest
song, which is consistent with a general transition sting. **0x85 is the
odd one**: villain reveals drawing an F major song.

So the mapping is well supported but NOT confirmed. The structural argument
is that there are exactly six cues (0x81-0x86), seven songs, nothing names
0x80 or 0x87, song 0 is the title the intro starts by itself, and 0x8n -> n
is the only assignment that uses every song exactly once.

**How to actually settle it:** run the DOS game and listen. All seven songs
are rendered to `audio/song0.wav` through `audio/song6.wav`, so reaching any
scene in the table above and hearing which one plays decides it. DOSBox is
not installed on this machine.

---

## Character creation: what a race and a career actually are

The creation screen is menu 1. Menus resolve through a pair table at
`0x13CC6`:

```
13CA0: asl.w   #$2, d0        ; menu number * 4
13CA2: lea.l   $13cc6.l, a2
13CA8: move.w  $2(a2,d0.w), d1
13CB8: adda.w  (a2,d0.w), a2
13CBC: bsr.w   $1391a
```

`base + second word` is the option list: a four-byte box (x, y, w, h) then
16-bit string ids ending at `0xFFFF`. Menu 1's list is at `0x13CDA`, box
19/22/34/22, and reads

```
human | desert runner | tinker | rocket jock | medic | warrior | rogue
| male | female | reroll stats | done
```

Strings come from a 134-entry offset table at `0x11DC4`, base-relative to
itself. Entries 19 to 22 are `martian`, `venusian`, `mercurian` and
`lunarian` -- **the Matrix Cubed race names are already in the ROM**.

The selection runs through a jump table at `0x606`:

```
005E6: moveq   #$1, d0
005E8: jsr     $13c9c.l       ; open menu 1
005F8: asl.w   #$1, d0
005FA: lea.l   $606.l, a0
00600: adda.w  (a0, d0.w), a0
00604: jmp     (a0)
```

| option | handler | what it writes |
|---|---|---|
| human | 0x006A2 | move `$24`=8, clears `$0C`, race 1 |
| desert runner | 0x006BC | move `$24`=10, `$2A`=3, `$2C`=1, race 2, falls into warrior |
| tinker | 0x006D6 | move `$24`=6, clears `$2C`, race 3, falls into medic |
| rocket jock | 0x00714 | career 1, `$26`=2, `$1E`=1250 |
| medic | 0x00728 | career 2, `$26`=2, `$1E`=1500 |
| warrior | 0x0073C | career 3, `$26`=4, `$1E`=2000 |
| rogue | 0x00750 | career 4, `$26`=2, `$1E`=1250 |

Race is set by `0x6E8` into `$17(a2)` and career by `0x704` into `$18(a2)`,
both small integers in the character record. `$1E` is the experience needed
for the next level and `$26` looks like the hit die.

**This is the good news: neither race nor career is an index into a
fixed-size table.** Each option is a handler that writes its own stat
modifiers inline. So adding one is not blocked by a three-entry table
somewhere; it is three concrete edits:

1. insert the string id into the `0xFFFF`-terminated list at `0x13CDA`
2. add an entry to the jump table at `0x606`
3. write a handler that sets `$17(a2)` and the stat fields

**The one real obstacle** is that the jump table is 11 entries, 22 bytes,
and the code resumes at `0x61C` immediately after it -- there is no room to
grow in place. The table has to move, and because the dispatch is
`adda.w (a0,d0.w), a0` the offsets are 16-bit signed, so a relocated table
must stay within 32 KB of its handlers. Expanded ROM above 1 MB is far too
distant; the table and any new handlers need space in the first 64 KB.

**Still unverified:** whether anything else reads `$17(a2)` and indexes a
three-entry table with it -- portrait choice and the combat figure are the
candidates. That has to be checked before a fourth race is safe.

---

## Picture directory: why expanding it kept failing

Expanding the ECL picture directory was written, shelved as "causes
intermittent crashes", and blamed on the wrong thing. Two separate faults:

**The one that was recorded.** `expand_pictures.apply` gave every added id
`ptrs[0]` as a placeholder, and `ptrs[0]` is id `0x20` -- the largest
picture in the cartridge, six frames and 12 KB. An id the directory lacks
takes the engine's own fallback at `0x082EC`, which picks something sensible
and retries, so *missing* ids were always safe; adding one turned a safe
miss into a hit on the biggest blob in the ROM. Real, but only a problem for
ids added without artwork.

**The one that was actually killing it.** After writing the id list the tool
did `at += len(ids) + 2`, which leaves the longword tables wherever the id
count happens to put them -- and an odd count puts them on an odd address:

```
ids 0x1B0000   ptrs 0x1B0043   meta 0x1B0147
```

The 68000 raises an address error on a longword read from an odd address, so
`movea.l (a1), a0` in the loader at `0x0B81E` froze the machine the moment
anything looked up a picture. **57 stock ids would have landed odd too**, so
this could never have worked at any id count. It is not something the added
ids provoked, and it is why the first attempt looked like an intermittent
data problem when it was a hard CPU fault.

Both directories are now expanded and aligned: 72 ECL pictures (57 stock
plus 15) and 9 VIEW big pictures (7 stock plus 2), with the rule that the
list of ids added and the list of ids injected are the same list.

The budget is real and worth recording. The portrait path sets `0xB4CD` and
the decompressor then targets a fixed buffer:

```
09DE2: lea.l  $b56a.w, a2     ; descriptor
09DE6: lea.l  $a0f6.w, a1     ; destination
09DF2: move.w #$370, d0       ; 880 tiles = 28,160 bytes
```

The injected portraits are 99 to 136 tiles each.

## The figure-sheet index is unbounded — this is the junk on the floor

The resource dispatcher splits on bit 7 of the id:

```
099BC: bclr.b #$7, d0      ; strip bit 7 and test it
099C0: bne.b  $9964        ; it was set -> the figure-sheet path
...
09974: asl.w  #$2, d0
09976: lea.l  $998c.l, a0  ; a table of exactly 12 entries
0997C: movea.l (a0, d0.w), a0
09982: bsr.w  $9bb6        ; decompress whatever that was
```

`bclr` leaves `d0` as `id & 0x7F`, so 0 to 127, and nothing checks it
against the twelve entries at `0x0998C`-`0x099BC`. Any id at or above `0x80`
whose low bits reach 12 reads a pointer from past the end of the table and
decompresses it into the figure buffer -- coloured junk on the floor where a
figure belongs. Countdown never trips it because its own ids are in range.

`tools/softfail.py` clamps it, using a helper written over the freed
`LoadFigure error` string at `0x09A02`.

## The ECL dispatch does not bounds check the opcode

```
03346: move.b (a2)+, d1      ; any byte, 0..255
03356: asl.w  #$1, d1
03358: lea.l  $336e.l, a3    ; 94 entries, ending at 0x342A
0335E: move.w (a3, d1.w), d1
03362: jsr    (a3, d1.w)
```

The transpiler used to emit `0xFF` for an untranslatable opcode, on the
grounds that it is outside the engine's 94 and therefore obvious in a dump.
It is also a wild jump: `0xFF` reads a word from `0x356C`, inside the
handler code well past the table, and jumps through it. There were 62, in
nearly every area. They are now a `GOTO` to the following instruction.

## Two decoders, and only one of them is the real one

`ecl.disassemble` is a linear sweep and stops at the first data region --
block 64 decodes 2.1% of its bytes that way, block 48 11.1%. That looks like
most of the game being dropped and is not: `ecl.disassemble_block` is
entry-point driven and gets 95.7% to 99.6% on the same blocks. Measure
coverage with the function the transpiler actually calls.

## Item ids need no translation at all

Both games' item tables are the same 91 entries in the same order. The DOS
one is 16-byte records in `ITEM0.DAX` and the Genesis one 10-byte records at
`0xF17D8`; bytes 2-3 (DOS) and 0-1 (Genesis) are indices into a shared name
fragment list, and decoding both gives 91 of 91 identical, `knife` at 1
through `mercurian battle armor` at 88.

This is the only table so far that matched outright. Skills, monsters,
sounds, walls and art all needed hand-built maps.

---

## Map coordinates: X and Y were crossed, and everything followed from that

The square lookup at `0x14CDC`:

```
14CDC: move.w  d4, d0
14CDE: mulu.w  #$10, d0
14CE2: add.w   d3, d0        ; index = d4 * 16 + d3
14CE4: lea.l   $b5a4.w, a0   ; walls, plane pair 0
14CE8: btst.b  #$2, d5       ; the direction picks the plane...
14CEE: lea.l   $b6a4.w, a0
14D00: lsr.b   d5, d0        ; ...and the nibble
14D02: andi.w  #$f, d0
```

and its caller loads `d3` from `0x9AF7`, `d4` from `0x9AF6`.

**Both games store maps row major.** Countdown's own maps are 100%
wall-consistent read as `y*16+x` and as low as 36% read as `x*16+y`, where
consistency means a wall between two squares appears in both of them. So
`d4` is Y and `d3` is X, and `DUNGEON_X` is `0x9AF7` while `DUNGEON_Y` is
`0x9AF6` -- the reverse of what this project had.

Read that way the delta table at `0x146E0` gives dx/dy of `(0,-1)`,
`(+1,0)`, `(0,+1)`, `(-1,0)`: **N, E, S, W, the same order DOS uses.** No
facing rotation, no vertical flip, no transpose.

Four earlier conclusions were built on the crossed reading and are all
wrong: the `+1` facing rotation, "y increases northward", the map flip, and
the explanation that facing south at y=2 looked off the bottom edge.

### Map layout, confirmed against play

- 16x16, row major, `y = 0` is north.
- Plane 0: north in the high nibble, east in the low.
- Plane 1: south in the high nibble, west in the low.
- Plane 2: per-square attributes.
- Plane 3: two bits per direction, read at `0x14CB4` from `0xB8A4` -- this
  is passability, separate from the wall graphic.
- Wall values seen: 1 is a plain wall, 13 is a door.

Checked against a DOS play session at the opening: at `(0,7)` the south wall
is 1 and the player saw a solid wall; one square east at `(1,7)` it is 13 and
they saw a door, which opens into `(1,8)` -- walled north, east and south,
open west, a two-square closet, which is exactly what they found.

## The engine has a built-in ECL debugger

The main menu's "debug ecl" at `0x04C7C` is `bchg.b #$0, $9bb9.w`, and the
dispatch loop tests that byte before every instruction:

```
0334A: tst.b  $9bb9.w
0334E: beq.b  $3354
03350: bsr.w  $438c
```

`0x0438C` opens a text window and prints the ECL program counter (`a2-1`)
followed by the next three bytes -- opcode and operands -- one instruction at
a time. It is reachable in a normal build from the menu.

---

## Wall codes are per-set graphics, and the two games disagree about them

A wall nibble is not "wall" or "door" -- it selects a graphic from the wall
set the area loaded. Cross-referencing every wall value against plane 3's
passability bits, over both games' own maps:

| value | Countdown passable | Matrix Cubed passable |
|---|---|---|
| 1 | 1.0% | 1.8% |
| 5 | 2.1% | 1.0% |
| 6 | **92.9%** | 40.7% |
| 7 | 70.0% | 69.9% |
| 12 | 100.0% (5 uses) | 41.6% |
| 13 | **0.0%** | 41.5% |

So Countdown's door is 6 and its 13 is a solid wall, while Matrix Cubed uses
13 for the door at the opening -- `(1,7)` south, which a play session walked
through into a two-square closet.

Transplanted maps therefore draw some doors as walls. **They are still
passable**: the engine takes passability from plane 3, at `0x14CB4`, which
is separate from the graphic nibble and transplants unchanged. A door that
looks like a wall can be walked through.

Mapping the codes properly means a table per wall set, since the meaning of
a value depends on which set is loaded, and the sets do not correspond
one-to-one either. Not attempted; the passability profiles above overlap too
much to derive it automatically -- 7 matches at 70% in both, but 6, 12 and
13 do not.

---

## Creature artwork: what is known, and the one thing that is not

Matrix Cubed's 36 creatures now have roster slots, names and figure records
of their own, but each still *looks* like the Countdown creature it clones.
Converting the artwork is the remaining piece. The measurements:

- A Genesis combat figure is the same container as a picture: count word,
  nametable size, flags, nametable, tile data. Decoded by
  `tools/genesis_pic.py`.
- Figure 0 is **117 tiles, 162 cells**, and its directory record's `chunk`
  byte is **18**, so the sheet is 18 tiles wide by 9 tall.
- At 24x24 per frame -- 3x3 tiles -- that is **eighteen frames**, six across
  and three down. Rendering one in false colour shows exactly that: a
  humanoid in a grid of poses.
- Matrix Cubed's combat sprites decode at **24x24**, so they drop in without
  scaling. `CPIC1.DAX` holds 108 and `COMSPR.DAX` 50; consecutive blocks are
  frames of the same creature, which is visible in a contact sheet -- five
  soldier poses in a row, then a crab, a scorpion, a dinosaur.

**The open question is the palette.** Figure blobs carry `flags = 0x0000`,
meaning no embedded palette -- unlike portraits, which set `0x0008` and
carry sixteen CRAM words. So the engine supplies the palette from somewhere
and the converted art has to be quantised to it, not to a palette of its
own choosing.

Ruled out so far: `0xF16AA` is not a palette table. Its words read `000A
455A`, `000A 4584` and so on, which are 32-bit pointers into the 0xA4xxx
region, not CRAM entries.

Sampling a rendered combat frame gives 16 distinct colours over the figures,
but that mixes the sprites with the floor behind them, so it is an upper
bound rather than the palette.

The next thing to try is the harness rather than the ROM: `tools/play.py`
can reach combat, so a stock figure whose tile indices are known can be
located on screen and each index read off against the colour it draws as.

### Reading the figure palette by asking the hardware

Two approaches failed. `0xF16AA` is a pointer table, not palettes. And
matching a known figure's tile indices against a rendered combat frame
finds nothing, because the engine composes a figure from hardware sprites
rather than drawing the sheet's nametable as it is laid out -- so the
arrangement on screen is not the arrangement in the blob.

What works is `tools/palette_probe.py`: replace a figure's artwork with a
test pattern, fight the creature under `tools/play.py`, and look. A first
pattern banded the index by pixel row and only ever revealed two colours,
because a figure is three tiles tall and the bands repeated inside each
tile. One flat index per 8x8 tile works: the enemy draws as a three by three
grid of solid colours.

The palette draws as red, green, navy, white, yellow, black, teal and dark
red, with the floor showing through wherever the index is transparent.

Still to do: pin which index is which colour. The engine's choice of tiles
is not the sheet's order, so the mapping cannot be read off directly -- it
needs either a probe per index, or working out how the sprite composer picks
tiles.

### The figure palette, index by index

Measured with `tools/palette_probe.py`, one probe per index: replace a
figure's artwork with a sheet that is entirely index N, fight the creature
under `tools/play.py`, and read the colour it draws as. Patterned probes
cannot give this, because the engine's choice of tiles is not the sheet's
order.

```
 0 transparent        4 (136,0,0)    dark red     8 (64,68,64)    dark grey    12 (232,68,64)  salmon
 1 (232,236,0) yellow 5 (136,0,136)  purple       9 (64,68,232)   blue         13 (0,136,0)    green
 2 (0,0,0)    black   6 (136,68,0)   brown       10 (64,236,64)   light green  14 (0,0,136)    navy
 3 (0,136,136) teal   7 (136,136,136) grey       11 (64,236,232)  cyan         15 (232,236,232) white
```

Saved index-ordered as `tools/figure_palette.json`.

### Matrix Cubed's combat sprites are already animation frames

`CPIC1.DAX` holds 108 sprites of 24x24. Consecutive blocks are poses of the
same creature, and the mean per-channel difference shows where one creature
ends and the next begins:

```
block 1 vs 2   10.3        block 4 vs 5   44.6   <- a new pose or creature
block 2 vs 3    9.8        block 5 vs 8   41.4
block 3 vs 4    7.9
```

The set also comes in two halves: block N and block N+54 are the same
creature in a variant, differing by 18 to 54 -- far more than neighbouring
frames and far less than unrelated creatures.

So there are frames to animate with. A Genesis figure sheet holds eighteen,
six across by three down, where Matrix Cubed offers roughly two to five per
creature, so the conversion has to place what exists into the slots the
engine animates and repeat to fill the rest.

## The wall-set tables, decoded

`LOADPIECES` divides its argument by three and indexes word offsets at
`0x51836`. Following them gives ten tables of **32 bytes** each, `0x20`
apart, and each one maps a **wall code 0-31 to a piece index 0-7**, with
`0xFF` meaning nothing is drawn:

    set 0: FF 01 02 03 04 05 05 00 06 06 07 07 FF FF 02 00 FF 00 02 01 ...
    set 1: FF 01 02 02 01 01 03 04 05 06 02 07 07 01 03 00 FF 00 01 01 ...
    ...
    set 8: FF 01 02 03 04 05 06 07 00 00 00 00 00 00 02 00 FF 00 02 00 ...
    set 9: FF 01 02 03 04 05 06 07 00 00 00 00 00 00 02 00 FF 00 02 00 ...

Sets 8 and 9 are identical and are the plain identity mapping. So a set owns
eight wall pieces and a table saying which code draws which.

Only five codes mean the same thing in every set -- 0 and 16 draw nothing,
1 is always piece 1, and 15 and 31 are always piece 0. The other
twenty-seven are set-dependent, which is what makes a transplanted map's
walls wrong: the code survives the transplant intact and then means
something else.

**That table is data we control.** Rather than rewriting Matrix Cubed's map
codes to suit Countdown's sets, the sets themselves can be rewritten so the
codes mean what the DOS game meant. Doing that needs `WALLDEF1.DAX` decoded
-- 2340 bytes per deco, eleven decos, same block ids as the deco arguments.
That is the next piece of work on walls and it is a data job, not an engine
one.

### Which decos the transplant actually uses

Logged from a real build, every `LOAD_AREA_DECO` the scenario issues:

    deco  5 x5    deco  7 x4    deco  3 x4    deco 11 x4
    deco 22 x3    deco 17 x3    deco  9 x2    deco 19 x2
    deco 15 x2    deco 13 x2

Thirty-one loads, ten distinct decos, **every one of them listed in
`tools/wallmap.py`**. `WALLDEF1.DAX` holds an eleventh, deco 1, which the
scenario never loads -- so the missing entry costs nothing.

## The sprite table, and the blank tile that sits one byte past it — CONFIRMED

Read out of a GENPLUS-GX savestate. The blob is flat: work RAM at offset
0x10 (byte-swapped within each word), the core's own sprite-table copy at
0x12024, VRAM at 0x12424, and the VDP register file at 0x22525. The
registers give the VRAM map:

    reg  2 = 0x28   plane A          0xA000
    reg  4 = 0x06   plane B          0xC000
    reg  3 = 0x3C   window plane     0xF000
    reg  5 = 0x76   sprite table     0xEC00
    reg 13 = 0x38   hscroll table    0xE000

The game draws its whole UI -- the 3D view frame, the right-hand panel and
the text box -- on the **window plane**, not on plane A.

Empty cells are filled with nametable entry `0x8774`: priority set,
palette 0, tile 0x774. The constant is at `0x1347A`, kept in `$b514`, and
streamed by the character filler at `0x95BE`. Tile 0x774 is at
`0x774 * 0x20 = 0xEE80`.

The sprite attribute table is 80 entries of 8 bytes at 0xEC00, so it ends at
0xEE80 — **tile 0x774 begins on the first byte after the last sprite.** An
81st sprite overwrites the blank tile, and nothing in the engine writes that
tile again, so the damage is permanent for the session: every empty cell on
every screen draws as coloured noise until the machine is reset.

The ordinary town screen uses 73 sprites. `PICTURE 255` draws the area's
default picture (chosen by the table at `0x82EC`), which is animated and
wants nine more. `VIEW` resets the sprite table on its way through
(`0x0AF22` -> `0x0860E` -> `0x09222`), which is why stock Countdown always
writes `VIEW / PICTURE / PRINTCLEAR / CONTINUE` in that order and never the
other way round.

### Reading VRAM out of a savestate

`Game.save()` returns the blob, so a probe is:

    V   = 0x12424                 # VRAM base in the savestate
    SAT = V + 0xEC00              # 80 entries, 8 bytes each
    tile774 = state[SAT + 80 * 8 : SAT + 80 * 8 + 32]

A clean tile 0x774 reads `00` then 31 bytes of `0x22`. Anything else is an
overflowed sprite table.

## COMBAT leaves the display disabled — CONFIRMED

The engine blanks the screen on its way out of a fight and does not turn it
back on. `0x085D6` writes `move.w #$8124,(a4)` — VDP register 1 with the
display bit clear — and only `0x0860E` (through `0x08608`, `move.w #$8164`)
sets it again. `VIEW` reaches `0x0860E`; `PRINTCLEAR`, `CONTINUE` and
`PICTURE` do not.

Read out of a savestate (VDP register file at offset `0x22525`) across the
spoils screen after a fight:

```
at the shop door    reg1=64   display on
spoils screen       reg1=64   display on
one button later    reg1=24   display OFF — and it stays off
```

Stock Countdown never notices, because its scripts end the event right after
a fight — `COMBAT -> EXIT` 15 times, `COMBAT -> ENCEXIT` 6 — and the walk
loop rebuilds the screen from scratch. Matrix Cubed's scripts carry straight
on, because the DOS engine restored the view by itself; `COMBAT / COMPARE /
IFLT / GOTO` is its commonest shape at 29 sites.

`tools/transpile.py` therefore emits `VIEW 0, 255` after every transplanted
`COMBAT` whose next instruction is not already one that ends the event.

## The 18 frames of a combat figure — CONFIRMED

Rendering stock figures frame by frame (`0x00` D.R. WARRIOR, `0x0C` PIRATE
WARRIOR, `0x1C` RAM H.S. ROBOT) gives the same layout every time:

```
 0-8    stand, aim, fire
 9-11   blank
12-14   stand again
15      going down
16      flat on the floor      <- what a killed creature is drawn as
17      stand
```

A DOS sprite block holds two poses and neither is a corpse, so a creature
built from one alone stays standing after it dies. `tools/inject_creature.py`
fills 15 and 16 with the standing pose turned a quarter turn — exact for a
24x24 creature, a squash for the oblong classes.

## Countdown's scripts and its engine share the flag region — CONFIRMED

`flagmap` allocated Matrix Cubed's story flags into "addresses Countdown's
own scripts use", on the reasoning that its campaign is being replaced so
its flags are free. That is true of most of them and false of some, because
the engine reads a few of the same addresses.

`0x97DC` is the one that showed it. Countdown's scripts write it, so it
looked free — but the `VIEW` handler writes 0xA8 or 0xA2 into it at
`0x03DFA`, and `0x082C6` reads it to choose which screen layout to draw:

```
082C4  move.b $97DC.w, d0
082C8  cmp.b  #$A2, d0     -> layout 1
082D2  cmp.b  #$A8, d0     -> layout 2
082DC  moveq  #3, d0       -> layout 3
```

It was handed to Matrix Cubed's `0x4C08`, the Rising Sun's day counter, so
leaving the hotel ran `ADD 1, [0x97DC], [0x97DC]` and incremented the layout
selector. The 3D view came back as garbage tiles under a spaceship control
panel.

`flagmap.engine_addresses` now reads every aligned word of the engine's own
code (`0x200-0x20000`) and treats any value in `0x9000-0x9FFF` as spoken
for, and `flagmap.mapped_targets` adds everything the transpiler assigns by
name. That over-counts — a constant in the same numeric range is not an
address — but the pool holds 3,587 slots for 385 flags, so the cost is
nothing and the alternative corrupts live engine state.

## A story flag must start at zero — CONFIRMED, the hard way

Every Gold Box story guard is "if this is not zero, I have already
happened":

```
COMPARE [flag], 0
IF_NOT_EQUALS
EXIT
WRITE_MEM 1, [flag]
... the scene ...
```

So a flag placed on RAM that does not power up at zero does not merely lose
state — the scene it guards **silently never fires**. Dr Romney on the
opening dock, square (4,2), event 20, was lost exactly this way: its flag
landed on `0x991A`, and `0x991A` reads 2 at the main menu before any script
has run.

The usable region is `0x96F6-0x9EF5`, and both ends are load-bearing:

* below `0x96F6` is the ECL code buffer (`0x6AF6-0x96F6`, the bounds the
  interpreter checks at `0x03308`) — work RAM there reads back as the
  running script's own text
* above `0x9EF5` is past the engine's start-up clear at `0x0115A`, so it
  holds whatever the machine powered on with: 266 non-zero bytes in
  `0x9EF6-0x9FFF`

Inside that region, 45 further addresses are still non-zero at the menu and
are listed in `flagmap.NOT_ZEROED`. That list is measured, not reasoned
about: boot the build, stop at the menu, read `0x96F6-0x9EF5` out of the
savestate and note every non-zero byte. Re-measure after any engine change.

With all three exclusions applied, 385 flags allocate with zero of them
landing on dirty RAM.

## `0xC04E` / `0x97AD` is computed from the map, and ours reads 0 — SOLVED, see below

This is the reason the opening dock stops advancing.

Matrix Cubed's scripts read DOS `0xC04E` in **80 places across the game**,
always comparing it against a small number, and write it in exactly one:
`INPUTNUMBER 3, [0xC04E]` in SSI's developer block. It is not a story flag
the scripts maintain — it is engine state they interrogate.

The mapping to Genesis `0x97AD` is sound: Countdown's own scripts read
`0x97AD` the same way (13 COMPAREs, an ONGOTO, an ONGOSUB) and both sides
top out at 12. The engine writes it at `0x0CCEA`:

```
0CCD2  moveq #0, d7
0CCD4  bsr.w $CCF4        ; sample the square
0CCD8  addq.w #1, d2      ; and its three neighbours,
0CCDA  bsr.w $CCF4        ; accumulating into d7
...
0CCEA  move.b d7, $97AD.w
```

`0x0CCF4` reads the drawn nametable at `0xA000`, so `0x97AD` is derived
from **what the map looks like around the party** — which walls and floor
types are there. Countdown's own areas produce 0-12. Driving the whole
opening dock and reading it at every step, our transplanted maps produce
**0, everywhere**.

Every gate on it therefore fails. On the dock:

```
00A3  COMPARE [0x97AD], 8 / IFEQ / GOTO   -> the coronation summons
00AE  COMPARE [0x97AD], 6 / IFNE / EXIT   -> a second 8-way square dispatch
```

So Dr Romney fires, the tannoy pages the party and sets its own flag, and
then nothing: "THE COMPUTER COMES TO LIFE. 'THE CORONATION IS ABOUT TO
BEGIN…'" is unreachable, and so is everything behind it.

This is the wall-graphics problem wearing a different hat — the transplanted
geometry does not draw the tile types the sampler counts — and fixing the
wall sets should fix this with it. Until then, 80 script gates across the
game are stuck on zero.

### The chain that has to run before `0x97AD` exists at all

Measured on the dock: `0xB556` and `0xB55A`, the two wall-piece tables, are
both **null**, and `0x0CCBA` returns without writing `0x97AD` when `0xB55A`
is zero. So the value is not wrong — it is never computed.

The tables are filled by the wall-set loader at `0x08360`, dispatched
through the jump table at `0x083D8` on `0xB52A`:

```
set 0 -> 08516    set 3 -> 08496    set 6 -> 084F8    set 9 -> 08516
set 1 -> 083F4    set 4 -> 084BC    set 7 -> 083EC
set 2 -> 08400    set 5 -> 084DA    set 8 -> 0850E
```

Only some of those populate `0xB556`/`0xB55A`. **Set 3 does not** — it fills
`0xB53E`/`0xB542` and falls through to the do-nothing tail — and set 3 is
what the dock gets.

`0xB52A` comes from `0x082AC`, which reads `0x9BBC` (the region) and
`0x97DC` (the wall selector). `0x9BBC` is set from VIEW's MODE through the
table at `0x03E22`:

```
mode   0  1  2  3  4
region 8  7  6  8  1
```

and `0x97DC` only ever becomes 0xA8 or 0xA2 from `VIEW 4, 0x71` / `VIEW 4,
0x72`. Matrix Cubed's block 17 uses neither: every VIEW on the dock is
`VIEW 0, 255`, so region 8, no selector, set 3, no piece tables, no
`0x97AD`.

Fixed so far: the mode-4 operands. Matrix Cubed uses 0x70 and 0x74 there
where Countdown uses 0x71 and 0x72, so the handler at `0x03DEA` fell through
and drew them as pictures instead of selecting a wall set. `artmap.WALL_SELECT`
now maps them, which reaches blocks 2, 32 and 48 (20 sites).

Still open: the dock itself, and every other area whose script never selects
a wall set. Those must be getting `0xC04E` from the DOS engine by some route
that does not go through a script-selected set -- most likely from the area's
own `LOAD_AREA_DECO`, which on the Genesis feeds a DIFFERENT loader
(`0x9AFB` -> `0x0976C`) that does not touch the piece tables. Reconciling
those two loaders is the next step.

## Operand counts have to match the HANDLER, not the DOS opcode — CONFIRMED

The interpreter reads exactly as many operands as its handler asks the
fetcher at `0x0404A` for, and cannot notice a disagreement. So where the two
engines differ, the difference is executed:

```
DOS                   ops        Genesis           ops
LOAD_AREA_DECO          3   ->   LOADPIECES          1    +2
DESTROY_ITEM            1   ->   DESTROY             2    -1
NPC_ADD                 2   ->   ADDNPC              2 (table said 0)
SPACE_COMBAT            4   ->   SPACECOMBAT         4 (table said 0)
COPY_PROTECTION         1   ->   PROTECT             -- unimplemented
PARTY_CHECK             6   ->   CHECKPARTY          -- unimplemented
SPELL                   3   ->   SPELLS              -- unimplemented
```

`LOAD_AREA_DECO` is the one that mattered. Its two spare operands were
emitted after `LOADPIECES`, and the first spare byte is `0x00` — `EXIT`. So
**every area's onInit stopped at its own wall-set load**, 33 sites.
`DESTROY_ITEM` failed the other way, reading the following instruction as
its second operand, 6 sites.

`ADDNPC` and `SPACECOMBAT` were counted off their handlers: `0x03AD4` is
`bra.w $488C` which fetches twice, and `0x03782` fetches four times. Both
are now in `genesis_disasm.HANDLER_SAYS` beside `CLEARBOX`.

The last three are not implemented at all. All three handlers are
`bra.w $4022`, and `0x04022` prints **"command not supported!"** and stops,
so mapping onto them turned an instruction that works in DOS into a hard
error. They are unmapped now and take the stub path, which steps over them.

`tools/transpile.py` reconciles the count on every instruction, padding or
dropping, and reports each one.

## `0xC04E` is `0x9AF8`, not `0x97AD` — CONFIRMED

The bank settles it. `0xC04B`, `0xC04C`, `0xC04D` and `0xC04F` are X, Y,
facing and the square's event byte, all four established against `0x9AF7`,
`0x9AF6`, `0x9AFA` and `0x9AF9`. `0xC04E` is the only one left, and
`0x9AF8` is the only slot left.

The old mapping to `0x97AD` was reasonable on its face -- Countdown's own
scripts read it the way Matrix Cubed reads `0xC04E`, and both top out at 12
-- but the two are computed differently and only one of them can work here:

```
0x97AD   <- 0x0CCEA   classifies the DRAWN tiles against the loaded wall
                      set's piece table.  Matrix Cubed's areas never select
                      a set that HAS one, so it reads 0 forever.
0x9AF8   <- 0x04244   reads the wall nibble in the facing direction out of
                      the map planes at 0xB5A4/0xB6A4 -- our own injected
                      geometry, carrying Matrix Cubed's own wall codes.
```

The dock's wall codes run 0-14 against the 0-12 the scripts compare, and the
value now varies with position and facing as it should: 6 facing north at
(11,4), 8 facing west at (0,4).

That last one is the coronation. The summons on the opening dock wants

```
009F  COMPARE [0x9AF8], 8 / IFEQ / GOTO
```

and standing at (0,4) facing west, after the tannoy has set its counter,
prints "THE COMPUTER COMES TO LIFE. 'THE CORONATION IS ABOUT TO BEGIN...'"
followed by de Sade.

One wrinkle worth knowing: `0x9AF8` is refreshed during the view draw, so
the step hook can run before it has been updated for the square just
entered. Walking into the wall re-runs the hook against the current value.
Whether DOS had the same ordering is not established.

### Why it appeared to work once

Before the flag allocator was corrected, DOS story flag `0x4C02` was being
allocated onto `0x97AD`. Scripts write that flag constantly -- 0, 1, 2, 3,
5, 6, 10 -- so `0x97AD` took arbitrary values and occasionally landed on 8,
firing the coronation at random. Fixing the allocation removed the accident
and made the real bug visible.

### The value is answered one action late

`0x9AF8` is recomputed at `0x04228`, and the movement path calls it as soon
as the new position is written:

```
054CE  move.b -$1B(a6), $9AF7.w     ; X
054D4  move.b -$19(a6), $9AF6.w     ; Y
054DE  bsr.w  $4228                 ; recompute
054E2  bsr.w  $4E00
```

The TURN path sets the facing and jumps straight past it:

```
0543C  move.b d0, $9AFA.w
05448  bra.w  $54E2                 ; skips the recompute
```

`tools/wallvalue.py` changes that displacement so the turn path lands on
`0x054DE` instead — two bytes. Turning now refreshes the value.

A lag remains on ARRIVAL: stepping onto a square and coming to face a
type-8 wall does not fire the gate, but pressing into that wall once more
does. So the facing must still be settled after the recompute somewhere on
the movement path. The practical effect is that walking UP to a wall does
nothing and walking INTO it works, which is at least a normal thing for a
player to do. Not yet chased down.

### Confirming the mapping against the maps

For every DOS block that compares `0xC04E` against a constant, is that
constant actually a wall code in that block's own map?

```
block  17  [0, 6, 8]            block  65  [8]
block  21  [2]                  block  96  [0, 5]
block  33  [0, 1, 2, 8, 9, 11]  block  97  [0, 3, 5, 12]  <- 12 not in map
block  34  [0, 6, 10, 11]       block 113  [3]
block  35  [0]
```

22 of 23 occur. That is the mapping confirmed from the data rather than from
the shape of the two variables' usage.

### What the values mean, from the scripts' own text

The strongest confirmation is not statistical, it is the text sitting next to
each comparison in Matrix Cubed's own scripts:

```
COMPARE [0xC04E], 0   ->  "A LOCKER ROOM MADE INTO A KITCHEN."   nothing there
COMPARE [0xC04E], 2   ->  "THIS DOOR IS SEALED SHUT."
COMPARE [0xC04E], 8   ->  "THE STAIRS LEAD " + up/down + ". DO YOU CONTINUE?"
COMPARE [0xC04E], 9   ->  "THE DOOR IS ALL BUT SEAMLESS."
```

So `0xC04E` is what the party is FACING, and the codes are features: 2 and 9
are kinds of door, 8 is a **staircase**. `0x9AF8` reads exactly that, which
settles the mapping.

It also explains the coronation. `COMPARE [0x9AF8], 8` means "standing at the
stairs", so de Sade intercepts the party at the staircase after telling them
to get to the coronation hall -- which is coherent design, not an arbitrary
square. It only LOOKS arbitrary in the port because the wall graphics do not
yet draw a staircase as a staircase, so the player cannot see what they are
standing in front of. That is the wall-set work, and this is another reason
to do it.

### What codes 6 and 8 are on the opening dock

Wall codes are per-deco, so the "8 is a staircase" reading taken from block
33 does not carry to block 17. The dock's own script says what its codes are.
Both live in the per-step hook:

```
80A3  COMPARE [0xC04E], 8 / IF_EQUALS / GOTO   -> the coronation summons
80AE  COMPARE [0xC04E], 6 / IF_NOT_EQUALS / EXIT
80B6  AND 63, [0xC04F], [0x7F79]
80CD  ON_GOTO [0x7F79], 8, {...}               -> a second, 8-way dispatch
```

and the map says where they are:

```
code 6, 21 sides: all four sides of (2,2) -- the cargo elevator -- and
                  (11,4)N and (12,4)N, which are the courtesy consoles
code 8, 11 sides: (3,0)N (11,0)N (0,4)W (11,5)W (12,7)E (6,9)N
                  (10,10)S (13,10)S (10,15)S (12,15)S (14,15)S
```

So **6 is a wall-mounted panel** -- consoles and the elevator, the things
you face to use -- and **8 is an exit**: almost every one is on the map
boundary or a division between wings. Most of the dock's other events guard
on `COMPARE [0xC04E], 0` instead, meaning "approached across an open side",
which is how the shop, the hotel, the portmaster and the residences work.

That makes the coronation coherent rather than arbitrary. De Sade tells the
party to get to the coronation hall, and the summons fires the next time
they face an exit -- eleven of them, spread around the dock, including the
south edge that leads to the hall. It is "he catches you on your way out",
not "stand on one hidden square".

It does not LOOK like that in the port, because the wall art is still
Countdown's: code 8 in set 1 draws Countdown's piece 5, whatever that is,
rather than a Matrix Cubed airlock. The ten 32-byte tables at 0x51836 map
code to piece and are ours to rewrite, but the pieces themselves are
Countdown's eight per set. Injecting Matrix Cubed's own wall art from
WALLDEF1.DAX -- 2340 bytes per deco, fifteen 156-byte records, one per wall
code 1-15 -- is the remaining job.

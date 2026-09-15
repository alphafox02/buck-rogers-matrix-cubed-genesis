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

### The PICTURE directory — CONFIRMED

Found by clustering: every ROM location holding a pointer to one of the 248
decodable pictures, grouped by constant stride. Four directories fall out:

| address | entries | stride | contents |
|---|---|---|---|
| `0x0998C` | 12 | 4 | 18x9 figure sheets |
| `0x09A14` | 52 | 8 | combat figures, `{ptr, id, chunk, flags}` |
| `0xF14F2` | **110** | 4 | **the `PICTURE` table** — 3x3 tiles, 24x24 |
| `0xF170E` | 50 | 4 | wall and dungeon pieces |

`0xF14F2` is indexed directly by the `PICTURE` operand and all 110 entries
decode, so **ids 0–109 are valid**. Rendering the ones Countdown's scripts
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

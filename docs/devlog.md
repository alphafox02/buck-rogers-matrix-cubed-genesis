# Development Log

Newest entries at the top. This is the narrative record -- what we tried,
what failed, and why we changed direction. Structured findings live in
`re_notes.md` and `formats.md`; this file is for the story.

---

## 2026-09-14 -- Day 2: both sides decode, and the live trace pays off

Ran mostly unattended overnight after Aaron got BlastEm's debugger working.

### The trace

BlastEm would not take piped input, but `di/x a2` at a breakpoint on the
opcode fetch prints the ECL program counter on every instruction -- so the
gaps between samples are exact instruction sizes. Aaron hand-fed `c` for a
few hundred iterations and pasted the output.

That trace did three things:

1. **Identified the running block as id `0x10`**, uniquely, from six
   independent instruction boundaries -- which independently validates the
   LZW decompressor and the `0x6AF6` code base.
2. **Caught a real bug.** `12 80 00 00` measured 4 bytes where the
   DOS-derived reading predicted 3. Genesis argument type `0x80` is a 2-byte
   string OFFSET, not DOS's inline packed string. Every string argument in
   every script had been mis-sized.
3. **Confirmed `FOR` at 2 arguments**, previously uncertain.

The nicest piece of evidence was accidental: the same `IFNE` at `0x7EF`
showed a 2-byte gap in one run and 1 byte in another. `0x7F0` is a one-byte
`EXIT`, and the conditional skips it or does not depending on the test. That
is only visible by running the same code twice.

It is now a regression test (`tests/check_trace.py`): 55 exact size matches,
9 explained by control flow, zero mismatches.

### Coverage: 11% to 94%

Two bugs, both reachability rather than decoding.

**Conditionals guard the following instruction.** `IF*` runs the next
instruction on success and skips it on failure, so both continuations are
reachable. Following only fall-through truncated every walk at the first
IF-guarded `EXIT` -- and Gold Box code is full of `IFEQ` / `EXIT` pairs.
Block `0x10` made it obvious: the walk died at `0x3F IFEQ`, `0x40 EXIT`,
while the trace proved execution continues well past `0x41`.
**11.1% -> 52.5%.**

**`ONGOTO` has two fixed arguments, not three.** With three, the first jump
target is eaten as a fixed argument, the tail reads one entry too many, and
the whole instruction fails -- and `ONGOTO` sits near the head of most large
blocks. Neither derivation method could have caught this: the static pass
counts fetcher calls inside the tail loop, the inference pass has no model of
a variable tail. **52.5% -> 94.4%.**

The same conditional fix applied to the DOS disassembler took it from 11.4%
to **98.4%**, past the 83.1% a naive linear scan had claimed while cheerfully
decoding data as instructions.

### Where the remaining gaps are

Checked rather than assumed. Block `0x03`'s unreached region is
`6a 00 64 36 00 / 6b 00 64 36 00 / 6c 00 64 0e` -- opcode `0x6A` is past the
94-opcode range and the incrementing first byte is a data table. Block `0x00`
mixes data with code reached from native routines rather than ECL jumps.
23 of 27 blocks are above 90%.

### The answer

`docs/compatibility.md`, generated from the full disassembly:

- 25,063 instructions, 71 distinct opcodes
- **58 of 71 opcodes covered, 90.64% of instructions**
- 13 orphans, and `INPUT_RETURN` is 76% of them -- it occupies the same slot
  as Genesis `CONTINUE` and has the same role, so it is very likely a direct
  map. Assume it and the unresolved surface is **2.25%**.
- `CALL` is the one real worry: it invokes a native routine, so call sites
  need individual attention rather than a table substitution.

### Lesson, third time

Static analysis found the formats; the emulator found the bugs in my reading
of them. Neither alone was enough. The trace was worth more than the previous
several hours of parameter guessing, and it took Aaron about ten minutes.

### Next

1. Reconciling the last gaps in blocks `0x00` and `0x03` (likely data tables).
2. An ECL **re-compressor**, to write blocks back into the ROM.
3. The map/GEO format, still untouched on the Genesis side.
4. A trace from combat or a menu, to exercise opcodes the intro never reaches.

---

## 2026-09-13 -- Day 1, part 2: the Genesis engine opens up

Part 1 solved the DOS side. This session went after the Genesis ROM, which
had been almost entirely unexplored.

### What we found

**The ECL virtual machine**, at `0x03344`. A textbook bytecode interpreter:
fetch a byte from `(a2)+`, index a 94-entry dispatch table at `0x0336E`,
`jsr` the handler, loop. `a2` is the ECL program counter.

**A single-step debugger SSI left in the retail cartridge.** The VM tests
RAM `$FF9BB9` before every dispatch and, if set, prints the instruction
address, the next six raw bytes, and the opcode mnemonic -- then waits for
a button press. One byte turns the shipped ROM into a script debugger.

**All 94 opcodes mapped** (`docs/opcode_map.md`), and a definitive
comparison against DOS: `0x00`-`0x1C` identical, first divergence at
`0x1D`, 60 of 77 shared slots aligned, `0x4D`-`0x5D` Genesis-only.

**The argument encoding is identical to DOS.** Decoding the shared fetcher
at `0x0404A` showed the same type-byte scheme, same size rules, same flag
bits. Arguments are even stored little-endian on a big-endian CPU -- the
scenario data came across from the DOS toolchain without byte swapping.
The one real difference: strings moved out of line, from inline packed text
to an offset added to the ECL base at `$FFB9A4`.

### What did not work

**Driving BlastEm headlessly.** Installed fine (0.6.3.4, runs at 59.9 fps),
but the `-d` debugger would not talk over a pipe, a pty, or a FIFO. Burned
real time on it.

**The naive tracer patch.** NOPing the branch at `0x0334E` forces the
tracer on, but it waits for a button on *every* instruction and ECL runs
before the screen is up, so the game boots to black. The patch tool is
correct -- its checksum routine reproduces the stock `0xD7B6` exactly --
the approach was just too blunt.

Self-inflicted: `pkill -f blastem` matched the shell command that contained
the string and killed the shell. Use `pkill -x`.

**Lesson repeated from part 1:** static analysis got the answer that the
emulator was supposed to provide, and got it faster. The argument encoding
came out of reading `0x0404A`, not from running anything. Reach for the
disassembly first.

### Where this leaves the port

The scenario translation problem is now fully characterised:

1. **Opcodes** -- table remap; a third of them already match
2. **Arguments** -- no change required at all
3. **Strings** -- extract inline text into a pool, rewrite args as offsets

That is a compiler back-end, not a research project.

### Resume here

Highest value next, in order:

1. **Confirm `0x11DC4` is the Genesis text pointer table.** It is a large
   monotonic 16-bit self-relative table pointing into `0x120D6`+. If it is
   the main string pool, that plus the out-of-line string finding gives us
   the whole text pipeline.
2. **Find how ECL blocks are stored in ROM.** We know `$FFB9A4` is the ECL
   base pointer -- find what writes it, and the resource table it indexes.
3. **Make the tracer usable**: patch out the button-wait at the end of
   `0x0438C` as well, or find the `"debug ecl"` menu entry (ROM `0x12651`).
4. **Entry-point headers** for the six Matrix Cubed ECL blocks that only
   decoded partially (36, 48, 49, 64, 65, 81).

Known unknowns unchanged: map/GEO format on Genesis, whether the resource
loader uses 32-bit ROM pointers, and the save mechanism.

---

## 2026-09-13 — Day 1: the asset pipeline is solved

**Where we started.** A project brief, a Genesis ROM, and the DOS Matrix
Cubed game directory. The brief listed eleven things as "not yet proven",
the most important being: *how data-driven is the Genesis Countdown engine,
and can new scenario content be inserted without rewriting the game?*

**Where we ended.** That question is largely answered, the entire Matrix
Cubed asset archive is extracted, and we have 3,430 PNGs of original 1992
artwork.

### What we found, in order

**1. The Genesis port runs the Gold Box ECL engine.** Searching the ROM for
strings turned up a table of 94 ECL opcode mnemonics at `0x452A`, plus
`"Bad ECL address"`, `"cant load ecl"`, `"Could not find geo!"` and — the
nice surprise — `"debug ecl"` and a leftover developer menu. The Genesis
version is not a bespoke console reimplementation. It is the same engine
with a different face. See `re_notes.md`.

**2. The DAX container and its compression.** Derived from first principles
by staring at header bytes: a `u16` index size, 9-byte records, then RLE
with a signed control byte. Validated across all 27 files — **611 of 611
blocks decompress to their exact declared size.**

**3. The image format, eventually.** This is where the day went sideways and
it is worth recording honestly.

The dimension fields fell out quickly (`byte0` = height, `byte1` = width/8,
confirmed because `height * width` divided every block exactly). TITLE
rendered correctly almost immediately — a legible SSI logo.

Then `BIGPIC1` rendered as *partially* correct: a recognisable overland map
in the lower portion, confetti noise in the upper. Three hypotheses were
tested and all three were wrong:

- 4bpp chunky (2 pixels/byte) — significantly worse
- VGA Mode X plane interleaving, two variants — worse
- a wrong pixel-data offset — ruled out by a per-row coherence profile,
  which showed no sharp transition anywhere in the block

At this point the temptation was to log it as unresolved and move on. That
was the wrong call, and we were pushed to keep going.

**The actual answer was in a repo already cloned to disk.** `ssi-engine`'s
`data/image/VGAImage.java` parses a header field we had labelled "not yet
identified": `color_base`. A block does not define all 256 palette entries.
It defines `color_count` entries starting at index `color_base`. For
`BIGPIC1` that is 224 entries starting at 32 — so rendering the palette from
index 0 shifted every colour by 32.

That is exactly why the image was *partially* legible: wherever the art used
a contiguous index range it still looked plausible.

**Lesson:** when a format is 90% right and the last 10% looks like noise,
suspect an off-by-N in the palette before rewriting the pixel decoder. And
read the source you already cloned before running experiments.

**4. DOS Countdown and DOS Matrix Cubed are the same engine build.**
Diffing the two `ssi-engine` game configs shows seven trivial differences —
MD5, umlauts, title offsets, menu label, two picture IDs, starting level.
The opcode table and the ~70-entry memory map are byte-identical.

**5. The Genesis and DOS opcode tables align.** Opcodes `0x00`–`0x1C` match
in exact order and meaning, including `SAVE` = `WRITE_MEM` where SSI's
internal name differs from the reverse-engineered one.

So the chain is: **Matrix Cubed ECL ≡ DOS Countdown ECL ≈ Genesis Countdown
ECL.** The only gap is one company's own console port of their own engine,
and it looks small. That was the project's central technical risk.

### What changed in the plan

- **"You need a pixel artist for months" was wrong** and is withdrawn. The
  job is converting existing art, not drawing new art. It is code, and the
  code now works.
- **The byte-identical ROM rebuild milestone is not needed.** We need to
  read and repack data, not reassemble code.
- **DOSBox matters far less than the brief assumes.** Campaign content is
  now inspected with Python, not by playing the game and screenshotting.
  DOSBox becomes a reference oracle, not a daily driver.

### Built today

- `tools/dax.py` — DAX container reader and RLE decompressor, with a
  self-verifying CLI
- `tools/gbimage.py` — Gold Box VGA image decoder
- `tools/extract_images.py` — bulk PNG extraction
- `docs/formats.md`, `docs/re_notes.md`, this log

### Next

1. ECL disassembler for `ECL1.DAX` (254 KB, 33 blocks, already
   decompressing). This turns the entire Matrix Cubed campaign into
   readable text and tells us the real opcode-usage profile.
2. Locate the Genesis ECL dispatch table and confirm the numbering.
3. Change one string in the ROM and boot it in BlastEm — proves the build
   loop.

### Credit and licensing

`farmboy0/ssi-engine` (GPLv3) supplied the `color_base` insight, the DOS
opcode enum, and the two game configs. Opcode numbers and RAM addresses are
facts, not copyrightable expression, and our implementations are written
fresh — but if any of its code is ever pasted into this tree, this project
becomes GPLv3. Keep the boundary clean.

---

## Later: the cartridge checksum, and the first content transplant

### The anti-tamper check

Hidden in the last 80 bytes of the ROM at `0x0FFFB0`: a 32-bit sum of every
longword in the cartridge, skipping the header checksum and the routine
itself, compared against `0x10D1310C`. On mismatch it blanks the VDP and
`bra.b $FFFFE` — hangs forever. That is the black screen.

Two things about how this was found are worth recording.

**The answer had been in my own trace for hours.** Addresses `0xFFFB0`
through `0xFFFC4` appear right at the divergence point in the very first
comparison I ran. I read them as RAM and moved on. They are ROM, eighty
bytes from the end of the cartridge.

**I could not read them until Capstone was installed.** Every earlier
attempt was pattern-matching byte sequences rather than disassembling, and
the routine uses `add.l (a0)+,d0` inside a `bgt` loop rather than the
`add.w` / `dbra` idiom I had been grepping for.

It is repaired, not defeated: because the check is a plain additive sum, one
spare longword in the zero padding at `0x1BBA4` absorbs the difference. The
cartridge still verifies itself and still passes. `rebuild_ecl` and
`patch_rom` apply it automatically.

### A misdiagnosis, reverted

While hunting the hang I had changed the compressor to avoid the KwKwK case,
theorising the hardware reconstructed it differently. That was wrong — the
hangs were the checksum all along. The change cost about 1.3% in size and
dropped byte-identity with SSI from 51/54 streams to 22/54. Reverted;
byte-identity is now 53/54 and the GEO stream is 38 bytes over SSI's rather
than 98.

### First content transplant

Matrix Cubed map 18 now lives in Genesis area `0x10`.

Maps need no conversion beyond dropping the DOS 2-byte id header, so the
work is: decompress the GEO stream, substitute 1024 bytes, recompress,
relocate, retarget the loader's pointer, repair the checksum.

Our recompressed stream does not fit its original footprint, so it moves
into the zero padding at `0x1BBA8` and the loader is retargeted:

```
0576E  lea.l  $8FA8D,a0   ->   lea.l  $1BBA8,a0
```

That relocation technique is what a full port needs regardless, since Matrix
Cubed's content is 1.61x the size of Countdown's.

Verified: the ROM reads back area `0x10` as Matrix Cubed map 18 byte for
byte, every other area is untouched, the checksum passes, and it boots to
985 distinct executed addresses — exactly the stock ROM's count.

**Not yet verified:** that the map renders correctly on screen. That needs
someone to play into the area. Booting proves the data is loadable and the
ROM is structurally sound, not that the geometry displays.

### Path A and Path B are not exclusive

With the checksum solved, the original cartridge becomes a test harness:
content conversions can be proven inside SSI's own engine before a
reimplementation exists. Everything validated there is trustworthy in a
reimplementation. Path A proves, Path B expands.

---

## PROOF OF CONCEPT: transplanted geometry renders in the Genesis engine

Confirmed on screen, on the second attempt.

### The first attempt failed as a test

`roms/countdown_mcmap.gen` put Matrix Cubed map 18 into area `0x10`. Played,
it looked unfamiliar — but neither of us had the stock layout memorised, and
Countdown's own areas are varied enough that "looks different" proves
nothing. Recorded as inconclusive. Comparing two plausible dungeons from
memory was never going to give a clean answer; that was a test-design
failure, not a result.

### The second attempt was built to be unmistakable

`roms/countdown_checker.gen` replaces the same area's map with a **synthetic
checkerboard** — every other square fully walled, in a strict alternating
grid. No level designer draws that, so there is nothing to confuse it with.

Stock area `0x10` is the spaceport tarmac: **open ground** with two small
one-square structures.

Aaron's report: *"i'm out on the tarmac and i'm running into walls getting
explosions"*.

The script is untouched, so the game still places him on the tarmac and still
runs the scripted air attack (`SOUND 0x2C`, `EXPLOSION 0x5`, `DELAY`, then
*"FIGHTERS SCREAM IN LOW FROM THE NORTH"*). Only the geometry changed — and
open ground now has walls in it.

The only difference between that ROM and stock is 1024 bytes of map data.

### What this validates, simultaneously

- the DAX container and its RLE
- the Gold Box four-plane map format on both engines
- the Genesis LZW **decompressor**, reimplemented from 68000 disassembly
- our LZW **compressor**, producing a stream the shipped engine accepts
- resource relocation into expanded ROM space above 1 MB
- retargeting a loader pointer (`lea.l $8FA8D,a0`)
- the anti-tamper checksum repair at `0x0FFFB0`

Every one had to be right at once. Any single mistake gives a hang or
unchanged geometry, not a different map.

A supporting signal noticed before play: the checkerboard ROM executes 1024
distinct addresses against stock's 985. Different geometry drives the
renderer down more paths.

### How it looked, and why

*"grey gravel looking ground with walls up that seem to slightly cut off"*.

The grey gravel is the stock tarmac wallset — `LOADPIECES` and the 32-byte
table at `0x51836` were untouched, so Countdown's own tiles are drawing
Matrix-Cubed-shaped geometry. That is exactly the separation the format
analysis predicted: geometry and graphics are independent.

The cut-off edges are the checkerboard being a pathological case rather than
a defect. Every walled square in it is an isolated one-square box with four
walls and no neighbours; the isometric renderer is built for connected runs
of wall, where corners join and faces occlude each other. 128 free-floating
cubes is geometry nobody designed for.

A real map, with rooms and connected walls, should render cleanly. Worth
re-testing with Matrix Cubed map 18 now that the pipeline itself is proven.

### What it does not yet show

Scripts and art. Maps were the easy content type — they convert by dropping
a 2-byte header. Scripts need the variable mapping (50 engine-shared
addresses, see `docs/variable_map.md`); art needs downconversion from
256-colour VGA.

### Still to do

Maps were the easy content type — they need no conversion beyond dropping a
2-byte header. Scripts need the variable mapping, and art needs
downconversion from 256-colour VGA. Neither is blocked, both are work.

---

## CONFIRMED with real content: Matrix Cubed map 18 renders as predicted

The checkerboard proved the write path. This proves the *decoder*.

`roms/countdown_mcmap.gen` carries the genuine Matrix Cubed map 18 in area
`0x10`. First look, it appeared unchanged — because the wall distribution
computed from our own decoder is:

```
walls per column (west->east):  9  9  9  8  7  3  3  3  3  3  3  3  2  0  0  0
walls per row  (north->south): 13 13 12  5  5  5  5  4  3  0  0  0  0  0  0  0
```

The southeast quarter of that map is genuinely empty — zero walls in the last
three columns and the bottom seven rows. Standing there, there is nothing to
see, and it looks exactly like the stock tarmac.

The prediction made from that table was: head northwest, expect a long
east-west wall run across the top and a complex of small rooms with doors in
the corner.

Aaron, having walked there: *"seems to be exactly as you described"*.

### Why this is the stronger result

The checkerboard showed that bytes we write reach the screen. This shows our
interpretation of the format is correct, because a layout predicted in
advance from the extracted data is what the engine actually drew. A decoder
with the wall planes transposed, the nibbles swapped, or the row/column order
wrong would still have produced *some* geometry — just not that geometry.

It also retroactively validates the ASCII floor plans in
`extracted/maps/`: they are what the game renders.

### The first attempt, in hindsight

The initial inconclusive test used this same ROM. The failure was not the
data but the vantage point — the player was standing in the empty quarter.
A test that depends on where someone happens to be standing is not a test,
which is what the synthetic checkerboard fixed by filling all 256 squares.

---

## 2026-09-14 (later): checksum, expansion, transplants, art, variables

Everything below happened after the map proof of concept.

### The anti-tamper checksum, and the mistake that hid it

A 32-bit longword sum of the whole cartridge lives in the **last 80 bytes**
at `0x0FFFB0`, compared against `0x10D1310C`. On mismatch it blanks the VDP
and `bra.b $FFFFE` — hangs forever. Rebuilt ROMs were hitting it.

Two things about finding it are worth keeping:

**The answer sat in my own trace for hours.** Addresses `0xFFFB0`-`0xFFFC4`
appear right at the divergence point in the very first comparison run. I
read them as RAM and moved on. They are ROM.

**Screen-capture testing was unreliable and I trusted it too long.** It gave
contradictory answers for the same ROM. Replaced with BlastEm's `-l` address
logging.

*Correction:* that was described here as deterministic. It is not. Stock
measured 985, 986, 1065 and 1069 across four runs — roughly 8% variance,
presumably from interrupt timing against emulator start-up.

The conclusions survive, but for a different reason than stated. A **hung**
ROM is invariant: the failing builds returned exactly 947 on every run at
both 25s and 60s, because a ROM stuck in a loop does the same thing every
time. 947 also sits below the entire observed stock range. So the signal is
the *absence* of variance plus a count below the floor — not a precise
instrument. Treat it as a liveness check, and do not read small differences
as meaningful.

Repaired rather than defeated — one spare longword absorbs the difference,
so the cartridge still verifies itself and still passes.

### Expansion

The sum covers `0x3FFEC` longwords, which is the first megabyte only, and
BlastEm maps ROM through `0x1FFFFF`. So the cartridge grows to 2 MB with
~1 MB of unchecked free space. Matrix Cubed's content needs 1.61x
Countdown's; expansion yields sixteen times the shortfall.

`tools/expand.py` relocates whole resource streams and retargets the three
loader pointers (`0x38CE2` ECL code, `0x42B0A` ECL text, `0x0576E` maps).

### Transplants, and a test-design failure

`countdown_mcmap.gen` put Matrix Cubed map 18 into area `0x10`. First
play-test looked different, then Aaron second-guessed it — rightly, since
neither of us had the stock layout memorised. Recorded as inconclusive and
an earlier over-claimed commit was amended.

The fix was a map that cannot be misread: a synthetic checkerboard, every
other square walled. Stock area `0x10` is open tarmac, so *"i'm out on the
tarmac and i'm running into walls"* was unambiguous.

Then the real map, with the wall distribution computed in advance —
northwest dense, southeast empty. *"seems to be exactly as you described."*
That is the stronger result: it shows the decoder is right, not merely that
writes reach the screen.

### Art

3,430 images converted (agent-assisted), then 173 more recovered after the
agent noticed `PIC1`/`SPRIT1`/`PIC7`/`PIC8` were being silently rejected —
about a third of the game's art, including every portrait. They use the
`VGADependentImages` format: different header, an EGA mapping table, XOR
frame deltas, and an RLE whose repeat branch also stores count-1.

Three real defects found and fixed in the converter, two of them mine:

- **Perceptual weights applied before squaring**, which squares the weights:
  blue was penalised by 0.012 instead of 0.11, so grey matched to purple.
- **Stale palettes** — k-means off-by-one, palettes built for the previous
  assignment.
- **Hue-destroying colour snap** (agent-found): per-channel snapping is the
  exact nearest neighbour under any per-channel metric, which is precisely
  why it can move two channels to the same level and turn brown into olive.

Measured the quality tiers: the **32X uses VGA's colour model** one bit
shallower, so it shows the original art essentially as drawn (error 1.85).
The Genesis version is good because the art only uses ~67 colours and per-8x8
locality is ~9.5 colours against a budget of 15.

### Variables

**94.7% of 10,019 variable references now translate.**

- 360 script-only flags reallocated. Required, not tidy: 255 sit below
  `0x8000` in DOS and Genesis ECL addresses sign-extend, so untranslated
  they resolve into ROM and writes vanish.
- 12 of 50 engine variables confirmed, each by a constraint only the right
  answer satisfies.

The productive method: an engine-shared variable is one the **engine writes
and scripts read**. Intersecting those two sets gives 20 candidates instead
of 259, and it reproduces every mapping found independently beforehand.

---

## RESUME HERE

State: 47 commits. No unknown formats remain in either game.

**Working and verified:** extraction, disassembly (DOS 98.4%, Genesis 94.4%),
compression both ways, ROM expansion to 2 MB, checksum repair, map
transplant confirmed on screen, art conversion.

**Next, in order:**

1. **The last 33 engine variables** (536 references, 5.3%). Led by
   `SAVED_TEMP_START` 0x4C00, `MONEY_NEO_ACCT` 0x4CE6, `DUNGEON_VALUE`
   0x4BE6. Method above; `tools/correlate_vars.py` generates leads but is
   not authoritative — confirm each against a forced constraint.
2. **The four orphan opcodes**: `CALL` (161 sites, needs per-site work),
   `PICTURE2`, `COPY_MEM`, `SELECT_ACTION`.
3. **Convert the 173 recovered portraits** through `convert_art.py`.
4. **Transplant a full area and play it** — that is the next milestone worth
   having, and it needs 1 and 2 first.

**Key facts worth not re-deriving:** ECL VM at `0x03344`, dispatch table
`0x0336E`, opcode names `0x0446E`, argument fetcher `0x0404A`, address
resolver `0x042E0`, checksum `0x0FFFB0` expecting `0x10D1310C`, code base
`0x6AF6`, GEO stream `0x8FA8D`, wall sets `0x51836`.

**Don't trust screen capture for boot tests.** Use `blastem -l` and count
distinct addresses in `address.log`; stock is 985.

---

## Matrix Cubed as a whole game, not a transplanted island

The previous build replaced exactly one area, and the report back was the
right one: *"it seems like i can't escape the area that's loaded."* That
was not a bug. Area `0x11`'s only exit is `NEWECL 0x12`, and area `0x12`
did not exist, so the engine had nowhere to go.

The fix was not to replace more areas but to stop replacing at all.

Reading the two loaders showed neither has a fixed area count — the ECL one
walks to a `0xFF` terminator, the GEO one loops on a count word it reads
from the stream. The id list could not grow only because the stream-1
offset table sat immediately behind it — and that table is already dead,
because `expand.py` relocates both streams above 1 MB and repoints
`0x38CE2` at the new one. The space was free the whole time.

So the directory is additive. `inject_area.py` now takes any number of
`<area>:<block>[:<map>]` specs in one pass and appends ids that are not
already present.

### The area graph closes on itself

Transpiling all 33 Matrix Cubed ECL blocks and collecting every `NEWECL`
immediate gives targets `0x02 0x12 0x13 0x14 0x20 0x21 0x22 0x23 0x24 0x25
0x26 0x30 0x31 0x32 0x40 0x41 0x50 0x51 0x52 0x54 0x5F 0x60 0x61 0x62 0x70
0x71 0x72`. Every one of them is a block that exists, under the convention
*area id = DOS block number in hex*. A graph that closes perfectly across
33 independently-decoded scripts is not a coincidence; it confirms both the
convention and the transpiler's operand handling at once.

More usefully: **all 33 blocks now transpile with zero unmapped
variables.** The devlog previously recorded 15 of 33 as fully translatable.
Routing the unconfirmed engine variables to inert storage closed the rest.

### What went in

31 blocks, as areas `0x10`–`0x72`. Two were deliberately left out:

- block 1, the DOS intro area, which would collide with Genesis area `0x01`
- block 2, which is SSI's combat test room — `"FIGHT HERE?"`,
  `"GIVE ALL NUMBERS IN DECIMAL."`, prompts for attack location and a
  `"IGNORE 'EQUIPMENT HIDE' OPTION?"` toggle. A developer scratchpad that
  shipped in the retail data.

Genesis areas `0x00`, `0x01` and `0x03` stay native so the boot and
character-creation path is untouched.

**No start-area patch was needed.** Genesis block `0x00` already does
`NEWECL 0x10` off its menu, and Matrix Cubed block 16 — area `0x10` — is a
30-byte entry stub that does `SAVE 1, [0x9E08]` then `NEWECL 0x13` into the
hub. The two games' entry points line up on their own.

### Two map-only areas

`LOADFILES` names a map id, and areas `0x31` and `0x32` load `0x34` and
`0x33` as sub-levels of their own region. Neither has an ECL block, so
nothing installed their geometry and the engine would have hit
`"Could not find geo!"`. `inject_area.py` now accepts `<area>:-:<map>` for
geometry with no script; DOS maps 51 and 52 fill them.

### Where it stands

```
ECL areas                39   (27 shipped)
GEO areas                30   of the engine's 32-entry ceiling
LOADFILES with no map     0
NEWECL with no script     0
checksum                 verifies
boot test          985 / 985 / 985 distinct addresses
```

The boot figure sits inside the stock 985–1069 band rather than the
947-with-zero-variance flatline a hung ROM produces.

Known and expected: walls draw from Countdown's art. `LOADPIECES` divides
its id by three to index ten wall sets, and Matrix Cubed's ids all fold
into that range — so the geometry is Matrix Cubed's and the texture on it
is Countdown's. That is the art pipeline's job and it is the next piece of
work, along with the 173 recovered portraits.

### First play session: empty text boxes are SSI's

An empty text box appeared early in play. It is authentic. `PRINTCLEAR ""`
is the Gold Box idiom for clearing the text window without printing, and
counting inline strings on both sides confirms it:

```
DOS Matrix Cubed   3818 inline strings,  62 empty
transplanted ROM   4116 string refs,     57 empty
```

The gap is blocks 1 and 2, which were deliberately left out.

A string audit also flagged 36 references past the end of a text pool, all
in areas `0x00`, `0x43` and `0x63` — stock areas never touched — with
values like `0x9AFC` and `0xA022` that are RAM addresses, not offsets.
`genesis_disasm` mis-types argument types `0x80`/`0x81` in that range. A
disassembler artifact, not a ROM defect, but worth fixing so the audit
stays useful as a regression check.

Confirmed working in play: area transitions, space travel, and combat
encounters driven by transplanted scripts.

### Every menu in the game was broken, and Salvation Port showed it

Disassembling the transplanted area `0x12` to check its services menu:

```
035C: HMENU    [0x9E6F], 0x5, "BAR", "CLINIC", "DEPOT", "TRAINING", "PORT"
03B2: ONGOTO   [0x6AF6], 0x6, [0x6EC0], ...
```

`HMENU` writes the player's choice to `0x9E6F`, and `ONGOTO` was reading
its selector from `0x6AF6` — `CODE_BASE`.

The transpiler classified jump operands **by instruction rather than by
position**. `ON_GOTO` and `ON_GOSUB` are jumps, so every memory operand
went through jump rebasing, including the first one, which is not a target
at all but the selector variable. It missed the layout and fell back to
`GEN_BASE`. The transpile report had been saying so all along —
`target 0x7F79 not in layout`, three times in block 19 — and 0x7F79 is the
variable, not an address.

295 `ONGOTO`/`ONGOSUB` instructions across the 31 areas, every one of them
wrong. Fixed by exempting operand 0 of those two opcodes from jump
rebasing.

### Why the ship could not move

The play report was "it says I can't move, then continue puts me in space".
Area `0x13` is Matrix Cubed's space hub, and its movement handler is a fuel
check:

```
07D6: WRITE_MEM 10, [0x7F79]          ; cost of the move
07F8: PARTY_SKILL_CHECK 46, ...       ; Astrogation
0807: IF_LESS -> ADD 10               ; a failed roll costs 10 more
081C: COMPARE 0, [0x4D1E]  IF_EQUALS -> "YOU CAN'T MOVE..."
0832: COMPARE [0x7F79], [0x4D1E] IF_GREATER -> the same
083E: SUBTRACT [0x7F79], [0x4D1E], [0x4D1E]
```

`0x4D1E` is fuel, and it was zero. Not a transplant defect: area `0x12` is
Salvation Port, and refuelling is a menu choice there, not automatic —

```
1191: "YOU ARE IN THE SALVATION PORT AREA."
11B1: SELECT_ACTION [0x7F79], 6
1254: "YOUR SHIP IS REFUELED."   -> WRITE_MEM 450, [0x4D1E]
```

The boot was entering at area `0x10`, whose stub jumps straight to the
space hub, skipping the port. Booting at `0x11` instead puts the player on
the tarmac with Salvation Port reachable, which is the game's own order.

### Genesis areas 0x00 and 0x01 are Matrix Cubed blocks 1 and 2

Worth recording because it was assumed otherwise. Stock Genesis area `0x00`
opens with `"DO YOU WANT TO START FROM SCRATCH OR USE THE JUMPER?"` and an
`HMENU` of `"JUMPER"` / `"START"` — the same opening as Matrix Cubed's
block 1. Genesis area `0x01` is the combat test room, the same as Matrix
Cubed's block 2. They are direct counterparts, not collisions, so blocks 1
and 2 can be transplanted after all.

---

## It runs

A play session reached Matrix Cubed's opening scene: Dr. Romney pushing the
papers into the party's hands, the Sun King's coronation, the Martian
assassins opening fire. Movement works, area transitions work, dialogue
works, skill checks work, combat fires.

The last bug was not in any of the tooling. The engine chooses its entry
area at `0x04146` and has four of them, and "load default team" — the
option a player actually picks — enters at area `0x10`, not `0x00`. Every
boot fix had gone into `0x00`. Matrix Cubed's area `0x10` is a 30-byte
stub whose whole body is `NEWECL 0x13`, so the game went straight to the
space hub every time, and the boot marker planted in `0x00` never printed.

Two things made that take far longer than it should have:

**A two-byte error in my own notes.** `re_notes.md` recorded the ECL loader
at `0x040CE`. It begins at `0x040D0`; `0x040CE` is the `rts` of the routine
above it. Searching the whole ROM for callers of `0x040CE` returned none,
which made the loader look unreachable and sent me looking at SRAM instead
of at the dispatch sitting twenty bytes further down.

**Not asking sooner.** The decisive fact — which menu option was being
chosen — was one question away for most of the session. A marker string in
the boot block, which is what finally settled it, cost five minutes and
should have been the first move once the symptom stopped matching the code.

### What the session established

- the resource directory is additive; 39 areas where the cartridge shipped 27
- the GEO loader's 32-byte stack buffer is the only hard ceiling, at 32 map areas
- all 33 ECL blocks transpile with zero unmapped variables
- DOS skill ids are the 84-skill tabletop list, 1-based, and map onto the Genesis 19
- `ON_GOTO`'s first operand is a selector, not a target — 295 menus were reading from `CODE_BASE`
- both games' area `0x00` is a developer warp harness, not a boot block
- `LOADFILES` names a map, `LOADPIECES` a wall set indexed by id/3

### Next

Art. All 3,430 images are converted and the whole set is 679 KB against
848 KB free, so it fits. The loaders need the same additive treatment the
ECL and GEO directories got: wall sets first, since they are on screen
constantly, then the title sequence, then portraits.

## Playing the story

A session reached the Salvation prologue and played it: Dr. Romney pushing
the papers over, the Sun King's coronation, the Martian assassins, and then
the Terran leader dragging Romney toward a groundcar with a three-way
choice — help Romney, call security, or aid the Terrans.

Choosing to aid them started a fight, which looked like a misrouted menu and
was not. The branch is a race check over the whole party:

```
0AD5: FOR           0x0, 0x7
0ADA: LOADCHARACTER [0x98EC]
0ADE: COMPARE       [0x9B23], 0x1
0AE4: IFNE
0AE5: GOTO          [0x75EC]     ; "'I WANT NO HELP FROM ANY SUBHUMAN
0AE9: ENDFOR                     ;   WRETCH.'" and into combat
```

DOS reads `[0x7C27]` at the same point, and the character record maps
`0x7C00 -> 0x9AFC`, so offset `0x27` lands on exactly `0x9B23`. The party
was not all Terran, so the offer was refused. Authentic 1992 behaviour, and
a good proof that the relocated character record reads correctly inside a
loop over party members.

Also confirmed working in play: the skill checks now name real skills
("team failed at perception" — DOS `Notice`, id 83, mapped to the Genesis
`perception`), three-way `WHMENU` choices route to the right branches, and
combat starts and resolves.

### What made the difference

Four fixes, in the order they mattered:

1. **Entry point.** "Load default team" boots area `0x10`, not `0x00`. Every
   boot change before that was dead code.
2. **`ON_GOTO` selectors.** 295 menus were reading their choice from
   `CODE_BASE` instead of the variable the menu had just written.
3. **Skill ids.** DOS's 84-skill tabletop list mapped onto the Genesis 19.
4. **Soft-fail on missing art.** The decompressor treated a missing resource
   as fatal. Four separate resource spaces each contained ids Countdown does
   not carry, and guarding them one at a time chased the same crash through
   several rebuilds. Pointing one branch at the routine's own clean exit
   ended it.

The third and fourth were only found because play reports kept contradicting
what the code appeared to say. Reading the error's callers first, rather
than last, would have saved most of an evening.

---

## Creature size: how a combat figure is actually built

A play report started this: the T-Rex in DOS "looked way bigger than other
things", and did the port scale it right. Answering it meant taking the
combat figure apart, and most of what this project believed about it was
wrong.

### Wrong turn one: the sheet width is not the frame shape

A figure record is eight bytes at `0x9A14` -- pointer, figure id at `+4`,
a width in tiles at `+5`, an animation index at `+6`, and a packed byte at
`+7`. Byte `+5` is only ever 18 or 36, and 43 figures have 18 while nine
have 36. That looked like the answer: two sizes, the big one twice as wide.

Rendering a 36-wide sheet as a 36-wide image gives scrambled body parts. It
is an atlas shape for the decompressor, nothing more. The frames are a flat
run of cells reshaped by the drawing code, and DESERT APE came out clean at
3 tiles wide by 6 tall -- so the conclusion flipped to "the large class is
24x48, taller not wider", which was reported and was also wrong. SAND SQUID
and ACID FROG were rendered the same way, looked like noise, and that should
have been the tell.

### The layout tables settle it

The size class is the **high nibble of byte 7**, and it picks a table of
byte offsets read one per cell:

    0xB742   00 06 0C 02 08 0E 04 0A 10 | 12 18 1E 14 1A 20 16 1C 22
    0xB754   00 0C 18 02 0E 1A 04 10 1C | 06 12 1E 08 14 20 0A 16 22

Halved, those are cell numbers, each group of nine in column-major order --
which is how a Genesis sprite reads its tiles. 0xB742's two groups are the
top and bottom halves of a 3x6 frame; 0xB754's are the left and right halves
of a 6x3 one. Only two routines in the entire ROM name either table,
`0xB58A` and `0xB5FA`, and they are byte-identical:

    cmp.b #2, d0 -> 18 cells, 0xB742      class 2   24 x 48
    cmp.b #3, d0 -> 18 cells, 0xB754      class 3   48 x 24
    else         ->  9 cells, 0xB742      class 0   24 x 24

Three classes, not two:

| class | frame | figures |
|---|---|---|
| 0 | 24 x 24 | 43 |
| 2 | 24 x 48 | 1 -- DESERT APE |
| 3 | 48 x 24 | 8 -- HEXADILLO, SAND SQUID, LG. E.C. GENNIE, RAM G.D. GENNIE, RAM ASSAULT BOT, RAM COMBAT BOT, ACID FROG, one unnamed |

Re-rendered at 6x3, ACID FROG is a fat green frog with a tongue that lashes
out in one frame. It had been sitting there the whole time.

### And DOS lines up better than expected

`CPIC1.DAX` carries its size in each block header:

| frame | count |
|---|---|
| 24 x 24 | 82 |
| 48 x 24 | 16 |
| 48 x 48 | 10 |

So 98 of 108 Matrix Cubed sprites land on an existing Genesis class with no
engine change at all. Only the ten 48x48 ones -- blocks 18, 21, 22, 29, 32,
146, 149, 150, 157 and 160, the dinosaur being 22 standing and 157 lunging
-- have nowhere to go. The port does *not* currently scale them right,
because there is no class that can hold them.

### What a figure really is on screen

    0C5BC: move.w  #$a00, d4      ; sprite size nibble 0xA = 3 wide, 3 tall
    0C5C4: move.w  d4, (a5)
    0C5D2: mulu.w  #$9, d1        ; nine VRAM tiles per display entry

Every combat figure is ONE hardware sprite, three tiles square. A bigger
creature is not a bigger sprite -- it is several entries in the display list
at `0xB0B4`, each its own 3x3 sprite, each drawing its own group of nine
tiles. The class decides how many and where:

- `0xC268` writes a slot width: 1 for class 0-1, 2 otherwise.
- `0xC2DA` advances the slot counter by that much, bounded by `$B1C4`
  (15 slots of 9 tiles from `$B1C6`, base 0x33A).
- `0xC358` lifts the first entry 24px for class 2, so a tall creature still
  stands on the floor.
- `0xC30E` builds the second entry, and `0xC32A` puts it 24px right for the
  wide class or leaves it below for the tall one -- swapping which group
  each entry draws when the figure is mirrored, so a flipped creature still
  reads left to right.

### Adding class 4

`tools/bigfigures.py` adds a 48x48 class: four entries, 36 cells, a new
quadrant-ordered table, and the slot accounting to match. Classes 0-3 keep
their stock behaviour -- the two stock bounds tests in the allocator do not
agree with each other (`beq` on the count for one slot, `bge` on count-1 for
two), so they were moved out whole and copied rather than rewritten.

Every instruction was hand-assembled and read back with capstone before
anything was believed.

### It is not proven yet, and here is exactly where it stands

`tools/bigprobe.py` gives a creature a sheet of flat colour tiles and fights
it, so the drawn shape can be measured off the screen instead of reasoned
about. RAM ASSASSIN drew as a 3x3 block of test colours -- the new sheet
loaded, the shape did not change.

Three control experiments, each a one-line patch:

1. Force `0xC3CA` to return class 3 for **every** figure. Nothing changed,
   including the party members.
2. Force both chains to 36 cells and the 6x6 table unconditionally. Nothing
   changed.
3. Class 2 and class 3 probes drew identically to class 0.

Which rules out the patch being subtly wrong and says something simpler: the
board these fights draw on does not go through `0xB58A`/`0xC20E` at all.
There is a second figure renderer around `0xF9C0`-`0xFBD8` that reads the
**low** nibble of byte 7 into an eight-entry table at `0x0FBF8`, four words
each, via `0x0FBA4`; `0xFA52` reads `$42(a2)` and `$23(a2)` and walks the
same `$B0B4` display list. That is the next thread.

Worth recording: `0x0C3D2`, `0x0CB48` and `0x0FBAE` have no callers anywhere
in the ROM under any call form. Their real entry points are a few
instructions earlier -- `0x0C3CA`, `0x0CB3E`, `0x0FBA4` -- each preceded by
an error string that made the `lea` look like the start of the routine.
Scanning for callers of the address you happen to be looking at will find
nothing and teach you nothing.

### Also worth not repeating

Capstone decodes past the end of the buffer you hand it. Disassembling
`0xC080` for 0x40 bytes printed `bsr.w $6b6a` for the instruction at
`0xC0BE` -- into the middle of a sine table -- because its displacement word
was one byte past the slice. The real target was `$B58A`. Always pass a few
extra bytes and filter by address.

## Chasing the figure renderer with counters instead of guesses

The 48x48 class went in and nothing on screen changed. Reading more code had
already been wrong three times, so this stopped reading and started
measuring: `tools/tracecalls.py` replaces a routine's entry with a jump to a
stub that bumps a counter in work RAM, runs the instructions it displaced,
and jumps back. `tools/play.py` reads the counters after a fight.

0xFFEF00 upward was checked first -- it stays zero through boot and a fight
in an untouched build -- so the counters cannot be mistaken for game state.
The first pass used byte counters and reported `0xC5BA = 1`, which is what
257 calls looks like after wrapping. Word counters from then on.

### What actually runs during a fight on the opening dock

| routine | calls |
|---|---|
| `0xC3FA` board render | 964 |
| `0xC9B0` figure stamp | 20 |
| `0xB670` tile blit | 134 |
| `0x9BB6` sheet decode | 11 |
| `0xC20E` combatant place | **1** |
| `0xB58A` figure blit | **1** |
| `0xC5BA` sprite emit | **1** |
| `0xC32A` second entry | **0** |
| `0xC142`, `0xFA52`, `0x108AA` | 0 |

Four RAM ASSASSINs are on the board and `0xC20E` ran once. Logging the class
it computed showed why: that one call was for figure `0x1E`, class 0 --
something else entirely. The monsters never go near it.

### So the board is not drawing figures as sprites at all

`0xC5BC` is the **only** `move.w #$0X00, Dn` in the ROM that loads a 3x3
sprite size, and it fires once per fight while the board renders 964 times.
The figures are stamped into a plane nametable by `0xC9B0`, which walks a
run-length script of (dx, dy, count) triples:

    0C9E8: move.b  (a0)+, d0     ; dx, or negative to end
    0C9F0: add.b   (a0)+, d3     ; dy
    0C9F2: move.b  (a0)+, d4     ; how many tiles
    0CA1E: asl.w   #$7, d3       ; address = dy * 128 + dx * 2
    0CA20: asl.w   #$1, d2       ; a 64-column plane

The shape of a board token lives in that script, not in the size class.

### Three experiments that agree

1. Force `0xC3CA` to return class 3 for every figure: nothing changes, party
   members included.
2. Force both chains to 36 cells and the 6x6 table unconditionally: nothing
   changes.
3. Substitute a genuine stock large figure -- DESERT APE record whole, class
   2, and ACID FROG, class 3 -- for the figure the first encounter spawns.
   Both draw as **24x24 crops of their own artwork**: the ape's head and
   shoulders, the frog's back. The art is right and the frame is truncated.

So on the ground-combat board every combatant is a 24x24 token regardless of
class, and the class machinery at `0xB58A`/`0xC20E`/`0xC358` belongs to a
different view -- `0xBFAE` calls `0xB58A` with class 1 hard-coded, which is
the shape of a panel portrait rather than a board token.

### Where class 4 stands

`tools/bigfigures.py` is written, every instruction read back with capstone,
the ROM boots, fights and keeps its checksum. It is correct on the path it
patches. It is not yet **reachable**, because the board does not use that
path, and claiming the port supports 48x48 creatures before one has been
seen on screen would be a guess dressed as a result.

Next: find what builds the script `0xC9B0` consumes. That is where a token's
tile footprint is decided, and it is the thing that has to grow for a
creature to be bigger on the board.

## The board draws nine cells, and three added creatures were losing half a body

Following the class-4 work with counters instead of guesses turned up a bug
that had nothing to do with 48x48 and everything to do with what the port
already ships.

### What the board actually reads

`tools/bigprobe.py` gives a figure a sheet of flat colour tiles numbered in
cell order, so whatever the engine draws can be read straight off the screen.
The drawn 3x3 came out as colours 11, 10, 9 / 14, 13, 12 / 1, -, 15 --
descending, which is cells 9, 10, 11 / 12, 13, 14 / 15, 16, 17 drawn
horizontally flipped.

So a board token is **nine consecutive cells, three to a row**, and the frame
index picks which nine. Not the column-major order the layout tables use,
and not anything the size class influences.

Substituting a stock DESERT APE (class 2) and ACID FROG (class 3) into the
opening encounter confirmed it: both draw as a 24x24 crop of their own
artwork. Rendering the ape's sheet as 24x24 frames shows why -- its real
frame is 3x6, so every nine-cell read is a top half or a bottom half.

### Which mattered here

`expand_figures` clones a donor figure's record whole, size class included,
and three of the thirty-six creatures this port adds clone a large donor:

    ASSAULT ROBOT  <- RAM ASSAULT BOT   class 3   48x24
    COMBAT ROBOT   <- RAM COMBAT BOT    class 3   48x24
    COYODORG       <- DESERT APE        class 2   24x48

All three were going to appear in combat as half a creature. Nobody had seen
it because none of them turn up in the opening encounter.

### The fix

`tools/rescale_figure.py` decodes each frame at its true shape, scales it to
24x24, and writes the figure back as a class 0 sheet -- eighteen frames of
nine cells, an atlas eighteen tiles wide.

Scaling is done on palette indices, not colours. The figure palette is
sixteen unrelated hues with no ramps, so averaging two pixels lands on
whatever index sits numerically between them. Each output pixel takes the
commonest non-transparent index in the box it covers.

Aspect-preserving scaling was tried first, centred and sat on the bottom
edge. It looks worse: a 48x24 robot becomes a half-height blob in the middle
of an empty token. Stretching to fill is what every stock 24x24 creature
does, and it is what reads correctly next to the party. The option is still
in the tool.

Verified on screen: the truncated version shows mirrored ape legs with no
head; the rescaled one is a complete beast at the same scale as the party
figures.

### Not shipped, and why -- and then a screenshot settled it

A play report pushed back: large creatures in Countdown are remembered as
**tall**, and if one is tall then whatever stands beside it has to be placed
clear of it. Then a screenshot of the real game turned up: a brown quadruped
on a desert board, plainly twice the height of the humanoids around it, with
the party spaced clear of it.

So the board does draw tall creatures, every substitution test above was
measuring the wrong thing, and the rescale is off for good.

## The size is on the MONSTER, not the figure

Every substitution changed the figure record and nothing else. The figure
record's class nibble is only half the story:

    monster record byte 0x23 (35):  1 = 24x24, 2 = 24x48, 3 = 48x24

Across all 87 monsters in the stream that pairing is exact -- class 0 goes
with 1, class 2 with 2, class 3 with 3, no exceptions. Set **both** and a
creature draws tall: figure 0x0F given DESERT APE's artwork and class 2, and
monster 0x0F's byte 35 set to 2, renders as full-height apes on the board,
three tiles wide and six tall, with the party member beside it normal size.
That is `art_preview/tall_proof.png`, and it matches the real screenshot.

### What byte 35 actually drives

    0x0CC9A   bounding box: size 2 -> d5 = 6, size 3 -> d4 = 6
    0x1050C   grid occupancy: size 2 takes an extra ROW, size 3 an extra
              COLUMN -- so a large creature stands on two squares
    0x14552   centre offset: 12 by default, 24 on the long axis
    0x15DD2   a tall/wide flag: 0xFF for 2, 0x01 for 3, 0 otherwise
    0x11B6E   a threshold, anything above 1 counts as large
    0x0CB1C   animation tweak, wide creatures only
    0x0CBAA   frame stride, anything above 1 counts as large
    0x0FA5A   feeds the animation geometry lookup

The engine's model is one grid square, or two -- vertically or horizontally.
There is no 2x2.

### Which means the port was never broken here

The three added creatures that clone a large donor -- ASSAULT ROBOT and
COMBAT ROBOT from 48x24 donors, COYODORG from a 24x48 one -- clone the
monster record too, so their byte 35 already agrees with their figure class.
Checked against all thirty-six: no mismatches. They draw tall already.

`tools/rescale_figure.py` would have shrunk three creatures that were
correct. It stays in the tree, off, because the scaling itself is sound and
something else may want it; it is not a fix for anything.

### And 48x48 is now a defined job

`tools/bigfigures.py` handles the drawing side: the layout table, the cell
count, the VRAM slots, and the third and fourth display entries. Setting
figure class 4 and byte 35 = 4 still draws 24x24, because the six sites
above only know 2 and 3. A 48x48 creature is one that stands on **two
squares by two**, so each of them needs a case:

    0x0CC9A   size 4 -> both d4 and d5 = 6
    0x1050C   size 4 -> an extra row AND an extra column
    0x14552   size 4 -> 24 on both axes
    0x15DD2   needs a third state, currently a two-state flag
    0x0CB1C   treat 4 like 3
    0x11B6E, 0x0CBAA   already correct, both test "> 1"

That is the whole remaining list, and it is short.

### Where 48x48 stood before this

A play report pushed back on this: large creatures in Countdown are
remembered as **tall**, and if one is tall then whatever stands beside it
has to be placed clear of it. That objection is right, and the engine
answers it -- `0xC358` lifts a class 2 figure 24px so it stands on the floor
rather than floating, and the allocator reserves two slots so the next
creature is not overlapped. None of that machinery exists unless tall
creatures are drawn tall somewhere. The nine large figures also carry
shadows at the bottom of their frames, art that only reads correctly whole.

So the rescale is written, verified and **off**. The truncation it fixes was
measured by substituting a figure record under a monster the engine spawned
as something else, which is not a real spawn, and three follow-ups failed to
show a tall draw either way:

- Reading `$B016`/`$B018` during a fight shows **one** combatant, figure
  `0x1E`, width 1 -- not any of the eight figures on screen.
- Giving figure `0x1E` a class 2 record changed **zero pixels**: it is
  tracked but never drawn.
- Forcing the monster loader to id `0x04` changed the encounter (a different
  combat UI came up, "ROARKE ATTACKS") without changing the artwork.

Whatever draws the figures on the board is none of the paths examined so
far. Shrinking three creatures on the strength of a test that does not model
a real spawn would trade a maybe-bug for a certain one, so `build.py` calls
it out and leaves it off until a large creature is seen truncated in
ordinary play.

### Where 48x48 stands

`tools/bigfigures.py` is still in the build and still inert. What the board
reads -- nine cells, three to a row -- is not what the class chain feeds it,
so making a creature bigger on the board means changing the board's read,
not the class tables. The class machinery belongs to some other view, which
`0xBFAE` calling `0xB58A` with class 1 hard-coded also points at.

That is a smaller and better-defined problem than it was two days ago, and
it is no longer blocking anything: every creature the port adds now draws
whole.

## A Matrix Cubed creature in Countdown's combat engine, at size

With the monster size byte found, the first DOS creature went in whole.
`tools/inject_creature.py` takes `CPIC1` block ids, quantises them to the
sixteen colours the engine gives a combat figure, fits them to a frame shape
and writes **both** fields that have to agree -- the figure record's class
nibble and the monster record's byte 0x23.

The dinosaur is `CPIC1` blocks 22 (standing) and 157 (lunging), 48x48 in
DOS. Fitted to the Genesis wide class it is a 48x24 crouching theropod with
its jaws open, and on the board it is plainly twice the width of the party
figures standing next to it. `art_preview/trex_zoom.png`.

Quantising to sixteen colours costs less than expected: the DOS sprite is
mostly two yellows and two browns with black outlines, and the figure
palette happens to carry all four.

A DOS block is a single pose, so the poses given are cycled to fill the
eighteen frames the sheet wants. That is enough to see a creature fight; a
real walk cycle needs the frame grouping in `docs/art_todo.md` finished.

### What is still missing for 48x48

The engine's model is one grid square, or two -- vertically or
horizontally. A true 48x48 creature stands on **two squares by two**, and
five sites decide that from the monster size byte. None has an external
branch into it, so all five can be rewritten in place:

    0x0CC9A   bounding box        24 bytes   size 4 -> both axes
    0x1050C   grid occupancy      34 bytes   extra row AND column
    0x14552   centre offset       26 bytes   24 on both axes
    0x15DD2   tall/wide flag      34 bytes   needs a third state
    0x0CB1C   animation tweak      1 byte    bne -> bcs, so 4 reads as 3

The fourth is the awkward one. The flag feeds `0x15F0C`, which for a tall
creature checks the square one row on and for a wide one the square one
column on, before letting it move. A 2x2 creature has to check three
neighbours, and that is pathfinding -- getting it wrong means monsters
walking through each other rather than merely looking odd.

So 48x48 is worth doing after the art pipeline, not before: ten DOS sprites
want it, and all ten already look right in the wide class.

## Which field really decides the shape, and why 48x48 is still out of reach

Two probes settled the first half. Figure class 0 with monster size 2 draws
**tall**; figure class 2 with monster size 1 draws **small**. So the monster
record's byte 0x23 is the field that matters and the figure record's class
nibble does not drive the board at all. `tools/bigfigures.py` keys on the
class nibble, which is why setting class 4 changed nothing: it was patching
a path the board does not use.

The second half is still open. Eight instructions in the ROM read
`$23(a2)` -- `0x0CB1C`, `0x0CBAA`, `0x0CC9A`, `0x0FA5A`, `0x1050C`,
`0x11B6E`, `0x14552`, `0x15DD2` -- and every one of them is a clean,
short, rewritable case statement over the values 1, 2 and 3. Instrumenting
all eight and fighting a genuinely tall creature gives the same counts as
fighting a small one: **zero, for all of them**. The creature still draws
tall.

So the size is read from a *copy* of the record, at some other offset, by
code not yet found. Searching work RAM at 0xFF9000 for the monster's name to
locate that copy turned up story text instead. Until the copy is found there
is no fourth case to add, and a size byte of 4 falls back to 24x24 -- which
is exactly what `art_preview/big48.png` shows.

### What the engine can do today, and it is not nothing

`art_preview/big_ten.png` puts all ten of Matrix Cubed's 48x48 creatures
through both native large shapes. Eight read best **tall** at 24x48 -- the
slime, the jellyfish walker, the dancer, the winged demon -- and the
dinosaur reads best **wide** at 48x24. Both are double the area of a normal
creature and both work now, with no engine change:

    inject_creature.py <in.gen> <out.gen> 0x0F:3:22,157

The DOS sprites do not fill their 48x48 square anyway -- most are a tall
figure or a long one inside it -- so the loss from the missing square class
is smaller than the numbers suggest.

## 48x48: nearly, and exactly what is left

`tools/bigcreature.py` extends the three routines a live fight showed taking
the monster size byte, each relocated whole into free ROM with a size 4 case
added, each rejoining the stock code where it left off:

    0x098B0   slot count     large claims one extra VRAM slot; 2x2 claims three
    0x0ADA6   frame shape    rows-1, cols-1, row stride; 48x48 is (5, 5, 12)
    0x142C4   grid squares   visits every square the creature stands on

The shape values were read straight out of the stock cases -- `(2,5,12)` for
48x24, `(5,2,6)` for 24x48, `(2,2,6)` for 24x24 -- so -6(a6) is rows-1,
-8(a6) cols-1, and -4(a6) the row stride in bytes, `(cols+1)*2`, which the
mirrored row writer at `0x0AEAE` confirms by adding it to `a1` per row.

**No fourth patch was needed.** A long detour went into changing the frame
stride at `0x0AE6A`, on the reasoning that a 36-cell frame has to step four
nine-cell units where an 18-cell one steps two. It does -- but the index is
already `4*anim + 2*facing`, which is **always even**, so the stock nine-cell
step lands on a 36-cell boundary by itself. Every attempt to "fix" the stride
made it worse, and the version with no stride patch at all is the one that
works.

**Verified harmless.** With the patch in and no 48x48 creature anywhere, a
fight on the opening dock is pixel-identical to the same fight before it --
zero pixels differ, twice measured.

### The splice was my data, not the engine

A play report caught it: "it looks like you are mixing two monsters together
in the 4 square." Exactly right, and literally so. The dinosaur was injected
as `CPIC1` blocks **22 and 157**, and 157 is not the dinosaur's second pose
-- it is the dancer. The two poses of the dinosaur are **22 and 150**. The
engine had been compositing a dinosaur and a dancer into one creature and
doing it correctly.

With `0x0F:4:22,150` the sheet is right: rendering it back out of the ROM
gives six clean frames of a standing theropod, head, jaws, body, legs, tail
and shadow, 48x48 each.

### What is still wrong: the lower half repeats the upper half

A second play report caught it -- "half his body bottom is below the floor
level". Two things were wrong and one is fixed.

**Fixed: the anchor.** The block at 0x0ADFC computes the drawing origin as
`gridX - d4`, `gridY - d5`, and a creature is drawn down and to the right of
it. A 2x2 creature therefore has to start one square higher or its feet hang
below the square it stands on. The size 4 case now does `addq.w #1, d5`
before rejoining, and the creature sits on the floor with the party.

**Not fixed: the rows.** Cropping one creature off the screen and putting it
next to the sheet frame it should be shows the board drawing the top half
twice -- head and shoulders, then head and shoulders again -- instead of top
then bottom. Reading the drawn tiles back as cell numbers agrees: rows 0-2
come from cells B, B+6, B+12 and rows 3-5 from B+28, B+34, B+40, when six
contiguous rows would be B through B+30.

The draw loop looks like it should already work:

    0AE7A: move.w -$6(a6), d2    ; rows-1 = 5, so six passes
    0AE84: jsr    (a2)           ; one row of cols+1 cells from a1
    0AE86: addi.w #$80, d3       ; next plane row
    0AE8A: dbra   d2, $ae7e

and every row writer advances `a1` by exactly `cols+1` cells -- `(a1)+` in
the plain one, `adda.w -$4(a6), a1` in the mirrored one, and -4(a6) is 12
bytes for six cells. So six rows from one base should be contiguous.

They are not. Matching each drawn tile row against the sheet answers it
precisely:

    screen row 0  <-  sheet cells  0.. 5   error 0.0
    screen row 1  <-  sheet cells  6..11   error 0.0
    screen row 2  <-  sheet cells 12..17   error 0.0
    screen rows 3-5                        nothing -- bare floor

Rows 0 to 2 are drawn **exactly**, six cells wide, from the right cells.
Rows 3 to 5 are not drawn at all; the floor shows through. So the six-cell
row width works and the six-row height does not.

And the deciding experiment: give size 4 the size 2 shape values --
`(5, 2, 6)`, byte for byte what the tall class uses -- and it still draws
only three rows, 24x26 px. The stock tall class with the same values draws
six. Identical shape words, different row count, so the row count is **not**
coming from -6(a6) alone. Something else keyed on the size byte gates it,
and size 4 falls into the normal case.

Which narrows the remaining work to one question: what else reads the size
byte and decides how many rows a creature gets. The candidates are the four
sites this tool does not yet patch -- 0x0CC9A, 0x1050C, 0x14552, 0x15DD2 --
though none of them registered a call in the traced fight, so it is more
likely a fifth that the trace missed because it sits behind a `>= 2` test
rather than an equality.

Everything else is in place and verified: the size byte, the frame shape
(six cells per row proven on screen), the grid squares, the VRAM slots, the
anchor, and the art pipeline that turns a DOS block into a 48x48 sheet.

Two hours went into rewriting engine code because a creature looked wrong,
when the creature looked wrong because it was two creatures. Check the
inputs before patching the machine.

### Two mistakes worth not repeating

`move.b #1, -$2(a6)` needs a full extension **word** for the immediate.
Emitting one byte shifted every instruction after it by one and hung the
machine on a black screen.

`add.b d0, d0` on a frame index overflows: `asl.b #2` has already multiplied
the animation step by four, so doubling can reach 0x80, which the following
`ext.w` reads as -128 and sends the sheet pointer backwards. Widen first,
then double. (This patch is gone now, but the lesson stands.)

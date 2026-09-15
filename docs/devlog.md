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

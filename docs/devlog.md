# Development Log

Newest entries at the top. This is the narrative record — what we tried,
what failed, and why we changed direction. Structured findings live in
`re_notes.md` and `formats.md`; this file is for the story.

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

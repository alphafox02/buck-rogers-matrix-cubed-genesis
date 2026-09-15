# Bulk art conversion: DOS VGA to Genesis

Every extracted Matrix Cubed image converted to Genesis tiles, palettes and
tilemaps. Method and evidence for the conversion itself are in
`docs/formats.md` ("Art conversion: VGA to Genesis"); this file reports what
came out of running it over the whole corpus.

Driver: `tools/convert_art.py`. Output: `extracted/genesis_art/<archive>/<id>.gart`
plus `extracted/genesis_art/manifest.json`.

```
python3 tools/convert_art.py --check --jobs 16
```

**3,430 images converted, 0 failures, 24 s wall clock on 16 cores.**

---

## The `.gart` container

One picture, ready to hand to the VDP. Big-endian, because the consumer is a
68000.

```
 0  4  magic 'GART'
 4  1  version (1)
 5  1  kind      0 background / 1 sprite / 2 tile
 6  1  palette_count  1..4
 7  1  flags     bit0 = index 0 is a keyed transparent colour
 8  2  width  in pixels
10  2  height in pixels
12  2  tile columns (width / 8)
14  2  tile rows    (height / 8)
16  2  unique tile count
18  3  the source key colour, r,g,b (zero when flags bit0 clear)
21  3  padding
24  .. palette_count * 16 CRAM words   (0000 BBB0 GGG0 RRR0)
..  .. unique_tiles * 32 bytes, VDP 4bpp order, high nibble = left pixel
..  .. columns*rows nametable words:  000 PP 00 <11-bit tile index>
```

The tile index in each nametable word is relative to the start of *this*
image's tile data; whoever uploads it adds the VRAM base. The key colour in
the header is kept only so a conversion can be audited against its source —
the hardware never sees it.

---

## Classification: what gets four palettes and what does not

A tilemap entry carries two palette bits, so plane art can draw from four
palettes. A hardware sprite's attribute word carries **one** palette index
for the whole sprite, so giving a sprite four palettes is meaningless — it
can only ever use one. The driver therefore sorts every image into one of
three classes.

| class | palettes | index 0 | which images |
|---|---|---|---|
| `background` | 1–4, measured | unused | BIGPIC1, TITLE, BACK1, and anything larger than 64x64 |
| `sprite` | 1 | keyed transparent | CPIC1, CHARS, COMSPR, 8X8D0, 8X8D1, CURSOR, and the SHIPS weapon/explosion frames |
| `tile` | 1 | unused | HITEK, LOTEK, MARSCOM, VENUSCOM, BORDERS, SHIPS console panels |

**Size rule.** A single Genesis sprite is at most 4x4 tiles. Nothing larger
than 32x32 can be one sprite, so the 64x64 cut is already generous; the
192x88 SHIPS pictures and the 176x176 starfield are plane art whatever
archive they live in. 40 images are backgrounds, 3,174 sprites, 216 tiles.

**Reserving index 0 is not a sprite-only concession.** Index 0 is
transparent in *any* tile on *either* plane — what shows through is the
backdrop colour register. So every class here gets 15 usable colours per
palette. The only difference between a sprite and an opaque tile is whether
some source colour is *mapped onto* that reserved index.

### The transparent key

The key is a property of the sprite set, not of a frame, so it is a fixed
per-archive table rather than a per-image guess. Each one was read off a
contact sheet of the whole archive:

| archive | key | what it is |
|---|---|---|
| CPIC1, CHARS, COMSPR | `(85,85,85)` VGA 8 | combat icons drawn on grey |
| 8X8D0 | `(0,0,0)` | sparks and lights on black |
| 8X8D1, CURSOR | `(255,85,255)` VGA 13 | wall-detail overlays on magenta |

A border-coverage heuristic was tried first and rejected: it works on CHARS
(coverage 0.90–1.00) and fails flatly on 8X8D1, where the median frame
scores **0.00** because the magenta sits in the middle of an 8x8 tile and the
wall pattern runs along its edge. An 8x8 image has only 28 border pixels;
there is nothing to measure.

SHIPS is the one mixed archive and does need a per-image test — weapon
effects keyed on black, console panels that merely sit on a dark bezel. The
black-border fraction separates them with a real gap, not a tuned threshold:

```
effects 014..025   0.87 .. 1.00      ->  sprite, keyed
panels  026..038   0.18 .. 0.66      ->  tile, opaque
```

Threshold 0.85. 12 SHIPS images are keyed, 13 are not.

**Why the key must be excluded before building the palette.** The key covers
about 70% of a typical CPIC1 icon, and `build_palette()` weights by pixel
frequency — handed the raw pixels it spends several of its fifteen entries
on shades of grey nobody will ever see. `convert_art.convert_keyed()`
filters the key out first. This is why the driver does not call
`genesis_art.convert()` for sprites.

### Palette count is measured, not assumed

Four palettes is the ceiling, not the answer. Half of this game's
backgrounds hold fewer than fifteen distinct *hardware* colours once
snapped, so splitting them four ways buys nothing — and every palette a
background does not claim is one the sprites drawn over it can have. Each
background is therefore converted at 1, 2, 3 and 4 palettes and the fewest
whose error is within 2% of the best is kept.

Result: **74 palettes across 40 backgrounds instead of 160.** Every TITLE
and BACK1 image but one collapses to 1 or 2. The six BIGPIC1 story scenes
keep 3 or 4, and earn them:

| image | 1 pal | 2 pal | 3 pal | 4 pal | kept |
|---|--:|--:|--:|--:|--:|
| BIGPIC1 112 | 11.63 | 9.37 | 8.29 | **7.93** | 4 |
| BIGPIC1 113 | 9.27 | 7.37 | **7.09** | 7.45 | 3 |
| BIGPIC1 117 | 12.45 | 9.04 | 10.15 | **8.80** | 4 |
| TITLE 004 | 10.50 | 8.37 | 8.47 | **8.14** | 4 |
| BACK1 001 | 5.29 | 5.25 | 5.25 | 5.25 | 1 |
| TITLE 002 | **3.42** | 3.66 | 3.66 | 3.66 | 1 |

That first column is the quantitative version of the claim in `formats.md`
that one palette is not enough: on BIGPIC1 112 going from one palette to
four cuts the error by 32%.

It also shows something the method's write-up does not mention: **more
palettes is not monotonically better.** BIGPIC1 113 is worse at 4 than at 3,
BIGPIC1 117 worse at 3 than at 2, TITLE 002 worse at 2 than at 1.
`convert_multi()` seeds by luma band and iterates to a fixed point, and that
fixed point is a local optimum — a coarser seed sometimes lands better.
Trying all four counts and keeping the winner is cheap insurance (it is why
the run takes 24 s instead of 10 s) and is worth more than any tuning.

---

## Cropping

**Zero images affected.** Every one of the 3,430 is already a multiple of 8
in both axes — 8x8, 24x24, 48x48, 88x88, 192x88, 304x120, 320x184 and so on.
The converter's `w - w % 8` crop never fires. The DOS art was authored on an
8-pixel grid, which is a small piece of luck for the port: no background
loses a column and no sprite loses a row.

---

## Size

| | bytes |
|---|--:|
| DOS pixels, 8bpp unpacked | 1,118,400 |
| the 15 `.DAX` files on disk (RLE packed) | 801,621 |
| Genesis tile data + tilemaps | 505,318 |
| Genesis palettes | 110,848 |
| total `.gart` including headers | 698,486 |

4bpp halves the pixel cost outright; tile deduplication and the tilemap give
some back. Against the DOS files as they actually ship, the converted art is
13% smaller — and that is *before* whatever compression the Genesis ROM's
own LZW does to it.

| archive | n | DOS 8bpp | tiles | tilemap | palettes | `.gart` | dedup | mean err |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 8X8D0 | 95 | 6,080 | 3,040 | 190 | 3,040 | 8,550 | 0.0% | 8.09 |
| 8X8D1 | 2836 | 181,504 | 90,752 | 5,672 | 90,752 | 255,240 | 0.0% | 5.69 |
| BACK1 | 20 | 154,880 | 62,112 | 4,840 | 800 | 68,232 | 19.8% | 6.45 |
| BIGPIC1 | 6 | 218,880 | 104,960 | 6,840 | 672 | 112,616 | 4.1% | 8.06 |
| BORDERS | 12 | 768 | 384 | 24 | 384 | 1,080 | 0.0% | 8.92 |
| CHARS | 72 | 41,472 | 20,128 | 1,296 | 2,304 | 25,456 | 2.9% | 8.67 |
| COMSPR | 50 | 28,800 | 10,432 | 900 | 1,600 | 14,132 | 27.6% | 6.37 |
| CPIC1 | 108 | 88,704 | 42,080 | 2,772 | 3,456 | 50,900 | 5.1% | 7.31 |
| CURSOR | 1 | 64 | 32 | 2 | 32 | 90 | 0.0% | 0.00 |
| HITEK | 53 | 30,528 | 12,128 | 954 | 1,696 | 16,050 | 20.5% | 6.95 |
| LOTEK | 52 | 29,952 | 11,232 | 936 | 1,664 | 15,080 | 25.0% | 7.21 |
| MARSCOM | 42 | 24,192 | 12,096 | 756 | 1,344 | 15,204 | 0.0% | 3.83 |
| SHIPS | 35 | 155,136 | 42,400 | 4,848 | 1,472 | 49,560 | 45.3% | 4.28 |
| TITLE | 4 | 132,096 | 45,920 | 4,128 | 224 | 50,368 | 30.5% | 4.06 |
| VENUSCOM | 44 | 25,344 | 12,672 | 792 | 1,408 | 15,928 | 0.0% | 5.53 |
| **total** | **3430** | **1,118,400** | **470,368** | **34,950** | **110,848** | **698,486** | **15.9%** | **5.90** |

### Deduplication

15.9% of tiles overall, but the headline number is misleading because it is
dominated by the 2,944 images that are a single 8x8 tile, where
within-image dedup cannot do anything by definition. Where there is room to
work it works well: SHIPS 45%, TITLE 31%, COMSPR 28%, LOTEK 25%, HITEK 21%.
BIGPIC1 is 4% — six hand-painted scenes with no repeated element, which is
what one would expect.

### The palette problem, which is the real size story

Look at the 8X8D1 row: **90,752 bytes of palettes for 90,752 bytes of
tiles.** 2,836 single-tile images each carry their own 32-byte CRAM block,
and the set ends up with 1,746 distinct palettes for 2,836 tiles. Per-image
conversion cannot see that these are one tile set.

Nor does cross-image tile dedup rescue it. Pooling every converted tile in
the corpus removes only 5% (14,699 -> 14,037), and for exactly this reason:
identical source tiles quantise to different indices because each was
measured against its own palette.

What a shared palette costs was measured directly on 8X8D1:

| scheme | palettes | bytes | mean err |
|---|--:|--:|--:|
| per image (shipped) | 2,836 | 181,504 | 5.69 |
| one palette for the whole set | 1 | 83,040 | 12.88 |
| four shared palettes, per-tile choice | 4 | 83,648 | 9.72 |

54% smaller, but the error nearly doubles even with four palettes — worse
than the worst individual sprite in the corpus. So the naive fix is not
worth taking, and the right answer is per-*wallset* palettes (8X8D1 is 13
DAX blocks, presumably one overlay set per dungeon theme), not one palette
for all 2,836. That is a separate pass and is not done here.

---

## Colour loss

Error metric: RMS distance between source and reconstructed pixel in the
same perceptual space `genesis_art` optimises (`_distance`, channel weights
0.30/0.59/0.11). Keyed pixels are excluded — a sprite's transparent area is
never drawn, and counting it would flatter every sprite with a big
background. Roughly, 0 is exact and 25 is a clearly wrong colour.

```
p0    0.00      p50   6.01      p90   8.05
p10   3.79      p75   7.08      p99   9.87
p25   4.99                      max  12.55
```

365 images score above 8, 30 above 10, none above 13. By class: backgrounds
5.77, sprites 5.89, tiles 6.09 — no class is systematically worse.

### Worst 20

| archive | id | kind | size | source colours | err |
|---|---|---|---|--:|--:|
| CPIC1 | 051 | sprite | 24x24 | 42 | 12.55 |
| CPIC1 | 159 | sprite | 24x24 | 25 | 12.49 |
| CPIC1 | 035 | sprite | 24x24 | 34 | 12.45 |
| CPIC1 | 157 | sprite | 48x48 | 31 | 12.38 |
| CHARS | 142 | sprite | 24x24 | 30 | 12.25 |
| CHARS | 005 | sprite | 24x24 | 28 | 12.16 |
| CPIC1 | 179 | sprite | 24x24 | 42 | 11.94 |
| CHARS | 144 | sprite | 24x24 | 26 | 11.86 |
| CHARS | 153 | sprite | 24x24 | 30 | 11.38 |
| CPIC1 | 029 | sprite | 48x48 | 31 | 11.32 |
| CPIC1 | 170 | sprite | 48x24 | 37 | 11.23 |
| CPIC1 | 017 | sprite | 24x24 | 27 | 11.21 |
| CPIC1 | 182 | sprite | 24x24 | 33 | 10.97 |
| CPIC1 | 064 | sprite | 24x24 | 28 | 10.75 |
| CHARS | 021 | sprite | 24x24 | 30 | 10.68 |
| CHARS | 141 | sprite | 24x24 | 30 | 10.64 |
| CHARS | 151 | sprite | 24x24 | 28 | 10.60 |
| CPIC1 | 042 | sprite | 48x24 | 37 | 10.59 |
| CHARS | 025 | sprite | 24x24 | 35 | 10.50 |
| CHARS | 155 | sprite | 24x24 | 29 | 10.48 |

Every one is a 24x24 or 48x48 figure sprite carrying 25–42 colours in 576
pixels. These are dense little pictures with no flat area to spend cheap
palette entries on, so the metric punishes them.

**The metric and the eye disagree, and the eye is right.** Side by side
(`_check/CPIC1_051.png`, `_check/CHARS_142.png`) the top scorers are
perfectly good: silhouettes intact, hair and clothing the right colours,
key cleanly transparent. Meanwhile `BIGPIC1 114` scores a mid-pack 8.23 and
is the most visibly damaged image in the corpus — its smooth skin gradients
posterise into flat patches. RMS per-pixel error does not see banding,
because banding is a *small* error repeated over a large smooth area. Do not
rank art by this number alone.

---

## Failures

**None.** All 3,430 images converted. No exceptions, no skips, no
truncations.

### But not all the game's art reached the converter

This run covers `extracted/images/`, which is what `tools/extract_images.py`
produced. Four image archives yield **zero** images because
`looks_like_image()` rejects every block in them:

| file | blocks | on-disk |
|---|--:|--:|
| PIC1.DAX | 46 | 400 KB |
| SPRIT1.DAX | 23 | 72 KB |
| PIC7.DAX | 1 | 7.7 KB |
| PIC8.DAX | 1 | 6.5 KB |

PIC1 alone is the largest image archive in the game — a third of its packed
art. The extractor is not silently wrong about these; they use a different
header. Every PIC1 block starts `58 00 0b 00 00 00 00 00 00 20`, which
decodes cleanly as a **12-byte variant** — `u16 height`, `u16 width/8`,
`u16 x`, `u16 y`, `u8 color_base`, `u8 color_count-1`, and **no
`image_count` field** — giving 88x88 with a 33-entry palette. SPRIT1 is the
same with `color_base` 2. The 33 palette bytes that follow are all < 64, as
6-bit VGA entries should be. Confidence: HIGH.

What is *not* solved is the pixel payload. After a 12-byte header and 99
palette bytes, PIC1 block 1 leaves 7,640 bytes where 88x88 needs 7,744, and
block sizes vary (7,548 – 8,552) for what should be fixed-size portraits. So
the pixels carry a second encoding on top of the DAX RLE. Confidence:
UNKNOWN. That is a format job, not a conversion job, and it is not done
here — but 46 character portraits are missing from the port until it is.

---

## Spot checks

`extracted/genesis_art/_check/` holds 29 side-by-side PNGs (original left,
reconstruction right, rendered from the `.gart` exactly as the VDP would
read it): the hardest and easiest backgrounds, one of each sprite and tile
family, and the eight worst-scoring images. Verdict after looking at all of
them:

**Good enough to ship, with one exception.**

* `BIGPIC1 113` (RAM warship), `BIGPIC1 112` (Mars overland), `SHIPS 000`
  and `SHIPS 004` (ship portraits), `SHIPS 128` (starfield), `TITLE 001`,
  `TITLE 003` — essentially indistinguishable at size. The claim in
  `formats.md` about the blue eyes holds: they are blue.
* `TITLE 004` (the Jupiter title screen, 210 colours) — very good. Banding
  is visible in the cloud bands and in the logo's blue gradient, but the
  picture reads identically.
* Sprites, all of them — very good. `CPIC1 001`, `CHARS 000`, `COMSPR 001`,
  `SHIPS 014`, and the worst scorers `CPIC1 051` / `CHARS 142`. Key
  transparency is clean, no fringing, no holes punched in artwork.
* Tile sets `MARSCOM`, `HITEK`, `LOTEK`, `VENUSCOM`, `BORDERS` — good.
  `BORDERS` shifts its brown ramp slightly, which is the worst of it.
* **`BIGPIC1 114` (the four-character scene) is the exception.** Skin tones
  posterise into flat patches, the woman's blue-green eye shadow is gone,
  and the background column changes hue mid-way. Still legible and
  unmistakably the same picture, but a player would see the difference. It
  carries 207 source colours that snap to 85 hardware ones and spreads them
  over four faces in four different lighting conditions — the one image in
  the corpus that genuinely wants more than 60 colours.

### The weakness the checks exposed

`BACK1 001` (`_check/BACK1_001.png`) shows it cleanly: a band of dark brown
in the original comes out **green**. That is not a clustering failure — the
region only holds 9 distinct colours, all 9 survive, and the palette is not
even full. It is `snap()`.

```
source  (80, 56, 48)   brown, R - G = 24
snap    (73, 73, 36)   R and G land on the same level -> olive
```

`snap()` takes the nearest of the eight levels per channel independently,
which is the exact nearest neighbour in RGB and therefore "optimal" —
including under `_perceptual`'s weights, since they are per-channel scalings
and do not change which grid point is closest. But nearest is not the same
as *right*: G 56 sits almost exactly between levels 36 and 73 (17 vs 20),
and taking 73 destroys the R > G relation that made the colour brown.
Choosing 36 instead costs 3 units and keeps the hue.

This is a property of the method, not a bug in the code, and it was left
alone — `genesis_art.py` is unmodified. But it is the single cheapest
quality win available: a hue-aware snap that prefers to preserve channel
ordering when two levels are nearly equidistant would fix the BACK1 greens
and probably several of the muddier BIGPIC1 patches, at the cost of
re-validating every conversion.

The second known weakness is structural rather than perceptual: terrain sets
(HITEK, LOTEK, MARSCOM, VENUSCOM) are converted one 24x24 tile at a time,
each with its own palette, but a combat map draws dozens of them at once
sharing four palettes on screen. Their per-image conversions are good in
isolation and will need a set-wide pass before any of them can actually be
drawn together. Same problem as 8X8D1, same fix.

---

## Keep the originals: art is a tiered problem, not a one-way conversion

The Genesis conversion is lossy and permanently so. It should therefore
never be treated as the archival form. The pipeline runs
**original -> target**, always, and the original PNGs in `extracted/images/`
and `extracted/images_vd/` are the master copies.

That matters because the three plausible targets differ enormously in what
they can show:

| target | simultaneous colours | palette space | bits/channel |
|---|---|---|---|
| DOS VGA source | 256 | 262,144 | 6 |
| **32X** | **256** | **32,768** | **5** |
| Genesis | 61 (4 x 15 + 1) | 512 | 3 |

**The 32X uses the same colour model as VGA**, one bit shallower per
channel. Measured on portrait `PIC1/001`, simply reducing 6-bit channels to
5-bit gives a mean perceptual error of **1.85** against the original — close
enough that the two are hard to tell apart side by side.

The same portrait converted for the Genesis loses its skin gradients to flat
patches, loses hair detail, and picks up a visible artifact where one tile
draws from an unsuitable palette.

### Consequence for the project

A 32X build does not need "restored" artwork — it needs the **original**
artwork with a trivial channel reduction. There is nothing to restore
because nothing was thrown away, provided the Genesis conversion is treated
as an output rather than a replacement.

This is the strongest practical argument for the 32X that the project has
produced. The 32X buys little in CPU terms for a turn-based RPG, but it
means SSI's 1992 artwork can be shown essentially as drawn, while the
Genesis build necessarily shows an approximation.

`tools/genesis_art.py` already separates palette construction from output
encoding, so a 32X encoder is a small addition rather than a rewrite: the
clustering step is simply skipped.

---

## Why the Genesis conversion looks better than the numbers suggest

"256 colours reduced to 60" overstates the problem in three ways.

**The art does not use 256 colours.** The VD header declares a 224-entry
palette, but across the 102 portraits actual usage is:

```
min 13    median 67    max 145
```

42 of 102 already fit inside 60 colours, so for those the only loss is
channel depth.

**Four palettes is 60, not 15.** A tilemap entry carries two bits of palette
index. Converting against one palette means 15 against a median of 67, which
is where the blue eyes turned cream. Four gives 60 against 67.

**Colour use is local.** In portrait `PIC1/001`, distinct colours per 8x8
tile:

```
mean 9.5    worst tile 26    budget 15
```

The average tile needs nine colours and may have fifteen. A tile covering
cheek holds skin tones; a tile covering background holds background tones;
they rarely mix within eight pixels. So the hardware is not approximating a
67-colour image with 15 — it is giving each small region a well-fitted 15,
and pixel art is locally coherent enough that this mostly works.

Sega built per-tile palette selection because that is how artists draw, and
SSI's artists were working with restricted ramps on VGA. The hardware and
the art suit each other.

### Where it therefore fails

Smooth gradients over large areas: one big region, many near-identical
shades, no locality to exploit. That is exactly the observed failure mode —
banding in a large flat red background, and flattening across a helmet's
grey gradient. Busy textured art such as foliage survives almost untouched.

Tiles at boundaries are the other weak spot: a tile spanning lit skin and
dark background needs colours from two ramps and gets neither well. The
purple artifact in dark backgrounds is this case.

---

## Injecting into the Genesis picture directory

`tools/inject_pic.py` writes Matrix Cubed artwork into the engine's own
picture table. It works end to end: 28 pictures covering 134 in-game uses,
compressed with `lzw_encode` (which reproduces an existing icon at exactly
its original 62 bytes), written above the relocated streams, with the
directory pointers at `0xF14F2` rewritten in place and the cartridge sum
repaired.

**The quality is much worse than the bulk conversion, and the reason is
structural rather than a defect.**

| | palette | mean error |
|---|---|---|
| `convert_art.py` to `.gart` | up to four, chosen per image | 10–14 |
| `inject_pic.py` into the ROM | the area's, fixed | **55** |

The container holds a tile count, a nametable and tile data — and no
colours. Colour comes from a separate table of 16-word palettes at
`0xF16AA`, selected by `0x9AFB`, which `LOADPIECES` sets to its id divided
by three. So injected art is quantised against a palette SSI tuned for
Countdown's own icons, and Matrix Cubed's blues, greens and purples have
nowhere to go. Earth renders as a dark blob.

Two other constraints compound it:

* Icons are **3x3 tiles, 24x24 pixels**, where the DOS portraits are 88x88.
  The Genesis port shows icons where DOS shows portraits; that is SSI's
  decision, not a conversion loss.
* Floyd-Steinberg **makes it worse here**, not better. Mean error rose from
  54.9 to 60.2 and the contact sheet looks visibly dirtier: at 576 pixels
  the dither noise reads as noise. Diffusion pays off over a 300x200
  background, not over a three-tile icon.

### What would actually raise it

Controlling the palette. The table at `0xF16AA` is an array of pointers,
so new palettes can be added the way areas were, and `PALETTE` (opcode
`0x51`) already exists to select one. The open question is whether the
picture draws on its own CRAM line or shares one with the walls — if it
shares, a palette tuned for a portrait would recolour the room around it.
That is the next thing to establish, and it is worth establishing before
injecting the remaining art.

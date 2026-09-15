# File Format Notes

All findings here were derived by inspecting the actual game files. Each entry
carries a confidence label per `PROJECT_BRIEF` conventions:
CONFIRMED / HIGH CONFIDENCE / PROBABLE / SPECULATIVE / UNKNOWN.

---

## DAX container — CONFIRMED

Used by every `.DAX` file in the DOS Matrix Cubed distribution.

```
u16   index_size_bytes          little endian
N x   9-byte records            N = index_size_bytes / 9
        u8   block_id
        u32  offset             relative to end of index
        u16  unpacked_size
        u16  packed_size
...   packed block data
```

**Evidence:** across all 27 `.DAX` files, every block's
`offset + packed_size` chains exactly to the next block's offset, and the
final block chains exactly to EOF. Implemented in `tools/dax.py`.

---

## DAX block compression — CONFIRMED

Byte-oriented RLE driven by a signed control byte:

| control (signed) | meaning                              |
|------------------|--------------------------------------|
| `s < 0`          | repeat the NEXT byte `-s` times      |
| `s >= 0`         | copy the next `s + 1` bytes literally |

**Evidence:** all **611 blocks across all 27 files** decompress to exactly
their declared `unpacked_size`. Zero failures, zero truncations. Verify with:

```
python3 tools/dax.py <path-to>/matrix/*.DAX
```

---

## Image blocks — CONFIRMED

### Header (10 bytes)

```
u8   height              pixels
u8   width / 8
u16  x_start             placement hint, 8-pixel units
u16  y_start             placement hint, 8-pixel units
u16  image_count         number of frames in this block
u8   color_base          first palette index this block defines
u8   color_count - 1     number of palette entries defined
```

Then `color_count` VGA palette entries at offset 10 (3 bytes each, 6 bits
per channel), then an unused gap, then the pixel data at:

```
len(block) - image_count * width * height
```

Pixels are 8bpp linear, one byte per palette index. No interleaving, no
planes, no per-row compression (the RLE is applied to the whole block).

### The colour_base trap

A block does **not** define all 256 palette entries. It defines
`color_count` entries beginning at index `color_base`. Indices below
`color_base` come from the game's base palette.

Rendering a block's palette as if it started at index 0 shifts every colour
and produces a confetti-like image that is *partially* legible wherever the
art happens to use a contiguous index range. This cost several hours of
wrong hypotheses (4bpp chunky, VGA Mode X interleave, wrong data offset)
before the field was identified. If an image looks like noise, check
`color_base` first.

Examples from Matrix Cubed:

| block                  | h   | w   | frames | color_base | color_count |
|------------------------|-----|-----|--------|------------|-------------|
| `TITLE.DAX` 1          | 72  | 320 | 1      | 16         | 240         |
| `BIGPIC1.DAX` 112      | 120 | 304 | 1      | 32         | 224         |

**Evidence:** implemented in `tools/gbimage.py`. Extracting all 27 `.DAX`
files yields **3,430 images** across 15 archives, including all six
`BIGPIC1` story scenes, 108 `CPIC1` combat sprites and the overland maps,
all rendering with correct colour. Cross-checked against the header parsing
in `farmboy0/ssi-engine` (`data/image/VGAImage.java`).

### Still unidentified

- The gap between the palette and the pixel data. Length varies; purpose
  unknown. Not required for decoding.
- The base palette that supplies indices below `color_base`. We currently
  seed the standard VGA 16-colour set, which is correct for every image
  inspected so far but has not been verified against the game's own table.
- `GEO1.DAX` (maps) and `WALLDEF1.DAX` (wall definitions) are not images
  and are correctly rejected by the extractor's header sanity check.

---

## Genesis ROM — see `docs/re_notes.md`

---

## Dungeon maps (GEO) — CONFIRMED, and they transfer almost 1:1

### Layout

A map is a 16x16 grid stored as four parallel 256-byte planes, indexed
`y * 16 + x`:

| plane | offset | contents |
|---|---|---|
| 0 | `0x000` | walls NORTH (high nibble) / EAST (low nibble) |
| 1 | `0x100` | walls SOUTH (high nibble) / WEST (low nibble) |
| 2 | `0x200` | per-square info, one byte |
| 3 | `0x300` | door flags: WEST bits 7-6, SOUTH 5-4, EAST 3-2, NORTH 1-0 |

A wall value of 0 is open; non-zero selects a graphic from the area's wall
set. A direction is a door when its flag pair is non-zero.

Note that 1026 bytes also fits a 32x32 grid at one byte per square, which is
the wrong answer — the structure was cross-checked against `ssi-engine`'s
`DungeonMap` rather than inferred from the size.

### DOS

`GEO1.DAX`, 25 maps, 1026 bytes each: a 2-byte id followed by the four
planes.

### Genesis

One continuous LZW stream at ROM `0x8FA8D`, read by the loader at `0x05766`:

```
0576E  lea.l   $8FA8D,a0      ; the GEO resource
05774  bsr.w   $9E76          ; initialise the decompressor
0577E  bsr.w   $9ED8 (2)      ; map count
0578A  bsr.w   $9ED8 (count)  ; id list
...    bsr.w   $9ED8 ($400)   ; then one 1024-byte map at a time
```

So: `u16 count`, `count` id bytes, then `count` maps of 1024 bytes. The
Genesis drops the 2-byte id header because ids are listed up front.

The stream decompresses to **18,452 bytes — exactly 2 + 18 + 18*1024** — and
the 18 area ids (`03 10 11 20 23 30 31 32 34 41 42 43 51 52 60 61 62 63`)
match the ECL area numbering.

### Why this matters for the port

**The map formats are identical apart from the 2-byte header.** Converting
a Matrix Cubed map to Genesis means stripping two bytes and appending the id
to the list. No geometry conversion, no re-authoring.

This settles the biggest open question about the isometric change: the
Genesis kept the DOS grid model and changed only the camera, exactly as the
`STEPFORWARD` / `HALFSTEP` opcodes suggested back on day one.

Both sets render as coherent architecture — rooms with internal walls, doors
in sensible places, open terrain. A wrong plane order would not produce
connected rooms.

---

## Wall sets — the one place the two engines genuinely diverge

### DOS: first-person display geometry

`WALLDEF1.DAX` holds 11 blocks of 2340 bytes = **15 wall types x 156 bytes**.
Each 156-byte record is a set of 8x8-tile index grids describing how to draw
that wall at three distances and three placements in the corridor view:

| field | grid | bytes |
|---|---|---|
| `farForward` | 2x1 | 2 |
| `farLeft` / `farRight` | 4x1 | 4 each |
| `medForward` | 4x3 | 12 |
| `medLeft` / `medRight` | 8x2 | 16 each |
| `closeForward` | 8x7 | 56 |
| `closeLeft` / `closeRight` | 11x2 | 22 each |
| `farFiller` | 2x1 | 2 |

156 exactly. Left/right pairs are mirrored (`farLeft 01 70 27 73` against
`farRight 01 71 28 72`), which is a useful structural check.

### Genesis: a lookup table

The isometric renderer computes its own geometry, so it needs only a mapping
from wall value to graphic. `LOADPIECES` (opcode `0x37`) resolves it:

```
158C4  divu.w  #$3,d0          ; wallset index = argument / 3
158CE  lea.l   $51836,a0       ; wall set table
158D4  adda.w  (a0,d0.w),a0    ; 16-bit self-relative offsets
158D8  move.l  a0,$B41A.w      ; -> the set
158DC  adda.w  #$10,a0
158E0  move.l  a0,$B41E.w      ; -> its second half
```

**10 wall sets of 32 bytes** at `0x51836`: 16 graphic indices followed by 16
attribute bytes, indexed directly by the map's wall nibble (0-15, with 0
meaning open and stored as `0xFF`).

The `divu #3` explains the leftover debug prompt at ROM `0x12EB0`,
`"Enter wallset as decimal (1,4,7..)"` — wall set arguments are `3n + 1`.

### What this means for the port

**Wall definitions do not transfer.** Matrix Cubed's 2340-byte blocks are
first-person corridor geometry that the Genesis renderer has no use for.

That is good news rather than bad: converting an area means authoring a
**32-byte** wall set — a graphic index and an attribute per wall value —
instead of converting 2340 bytes of view geometry. The map's wall nibbles
already index it directly.

This is the only content type so far where the two engines are structurally
incompatible, and it is the cheapest one to redo.

---

## Art conversion: VGA to Genesis

The gap the conversion has to close:

| | DOS | Genesis |
|---|---|---|
| simultaneous colours | 256 | 16 per palette, 4 palettes |
| colour space | 262,144 (6 bits/channel) | 512 (3 bits/channel) |
| storage | 1 byte per pixel | 4 bits per pixel, 8x8 tiles |

`tools/genesis_art.py` does it in three steps, and the order matters:

1. **Cluster in a perceptual space.** Plain RGB distance overweights green
   and turns skies muddy. Median cut weighted by pixel frequency, so entries
   go where the picture spends its area rather than on a few specular
   highlights.
2. **Snap to hardware colours after clustering, not before.** Quantising
   first collapses distinct shades together and the clusterer can no longer
   tell them apart.
3. **Assign pixels**, then pack to 4bpp tiles and deduplicate.

### Use all four palettes

A tilemap entry carries two bits of palette index, so a background can draw
from **four** 15-colour palettes — 60 colours, not 15. Converting against a
single palette wastes three quarters of the hardware.

The difference is not subtle. On `BIGPIC1` 113 (the RAM warship), a single
palette spends every entry on orange hull and the character's **blue eyes
come out cream**. With four palettes — tiles clustered by colour content,
each picking the palette that represents it best — the eyes are blue, the
exhaust flames keep their yellow core, and the starfield stays clean.

`convert_multi()` seeds the clustering by mean tile luma, which separates
sky from subject far better than an arbitrary start, then iterates
assignment and palette construction to a fixed point.

### Dithering is off by default

Floyd-Steinberg buys smoother gradients at the cost of a speckle that reads
as noise at Genesis resolution, and it is clearly worse on the test image —
the starfield turns grainy. SSI's own Genesis art does not dither.

---

## "VGA dependent" images — the portraits — CONFIRMED

`PIC1.DAX` (46 blocks, 400 KB), `SPRIT1.DAX` (23), `PIC7` and `PIC8` are not
the plain VGA images `gbimage.py` handles. They were silently rejected by the
extractor's header sanity check for roughly a third of the game's art,
including every character portrait.

The game configuration names the format: Matrix Cubed sets
`picture.format=VD` and `sprite.format=VD`.

### Layout

```
u16  height
u16  width / 8
u16  x placement
u16  y placement
u8   image_count - 1
u8   colour_base
u8   colour_count
...  colour_count * 3 bytes of 6-bit VGA palette
...  colour_count / 2 bytes mapping VGA indices to EGA
4    unrecognised
u8   index of the base image
1    unrecognised
...  3 bytes per image, packed sizes
...  RLE data for every frame, concatenated
```

Every block is 88x88 with 224 colours based at 32. `PIC1` holds one frame
per block; `SPRIT1` holds three.

### Two differences that matter

**The RLE is not the container's.** It is a near-relative in which the
repeat branch *also* stores count-1, so a run is `count + 1` long in both
branches. Decoding with the DAX container's rule desynchronises after the
first run — which is why four brute-forced variants all failed before the
format was read properly.

**Frames after the first are XOR deltas** against a designated base frame.
That explains block sizes varying from 4,782 to 22,049 bytes for what are
nominally fixed-size portraits: a delta of a near-identical frame compresses
to almost nothing.

### Result

**71 of 71 blocks decompress to exactly the expected size**, yielding 173
images: character portraits, alien and monster art, and three-frame sprite
animations.

Structure cross-checked against `farmboy0/ssi-engine`
(`data/image/VGADependentImages.java`).

### Lesson

This is the third time in the project that reading an existing
implementation beat guessing. The DAX palette `colour_base` field, the
dungeon map's four-plane layout, and now this were all solved in minutes by
opening a file, after considerably longer spent inferring from bytes.

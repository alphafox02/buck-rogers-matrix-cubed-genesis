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

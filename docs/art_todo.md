# Art still to inject

Every Matrix Cubed art reference the Genesis cartridge cannot satisfy.
`tools/artmap.py` currently rewrites these to `0xFF` ("no picture") so the
loader does not crash -- see the commit that added it. This is the list of
what has to be injected to remove that stopgap, and where each one is used.

Converted sources live in `extracted/genesis_art/<archive>/<id>.gart`.

**143 references, 22 distinct resources.**

| opcode | id | uses | converted source | size |
|---|---|---|---|---|
| `PICTURE` | `0x1D` (29) | 39 | `CPIC1/029` | 0.8 KB |
| `PICTURE` | `0x39` (57) | 26 | `CPIC1/057` | 0.4 KB |
| `PICTURE` | `0x37` (55) | 20 | `CPIC1/055` | 0.3 KB |
| `PICTURE` | `0x62` (98) | 15 | *not found* |  |
| `PICTURE` | `0x1E` (30) | 7 | `CPIC1/030` | 0.4 KB |
| `PICTURE` | `0x02` (2) | 5 | `CPIC1/002` | 0.4 KB |
| `PICTURE` | `0x50` (80) | 3 | *not found* |  |
| `PICTURE` | `0x20` (32) | 3 | `CPIC1/032` | 1.2 KB |
| `PICTURE` | `0x6A` (106) | 3 | *not found* |  |
| `PICTURE` | `0x17` (23) | 3 | `CPIC1/023` | 0.4 KB |
| `PICTURE` | `0x6B` (107) | 2 | *not found* |  |
| `PICTURE` | `0x66` (102) | 2 | *not found* |  |
| `PICTURE` | `0x67` (103) | 2 | *not found* |  |
| `PICTURE` | `0x38` (56) | 2 | `CPIC1/056` | 0.3 KB |
| `PICTURE` | `0x54` (84) | 2 | *not found* |  |
| `PICTURE` | `0x1F` (31) | 2 | `CPIC1/031` | 0.4 KB |
| `PICTURE` | `0x04` (4) | 2 | `CPIC1/004` | 0.4 KB |
| `PICTURE` | `0x65` (101) | 1 | *not found* |  |
| `PICTURE` | `0x68` (104) | 1 | *not found* |  |
| `PICTURE` | `0x6F` (111) | 1 | *not found* |  |
| `PICTURE` | `0x60` (96) | 1 | *not found* |  |
| `PICTURE` | `0x52` (82) | 1 | *not found* |  |

## Where each is used

| area | DOS block | offset | opcode | id |
|---|---|---|---|---|
| `0x00` | 1 | `0x0B58` | `PICTURE` | `0x39` |
| `0x00` | 1 | `0x0BA3` | `PICTURE` | `0x39` |
| `0x11` | 17 | `0x010D` | `PICTURE` | `0x62` |
| `0x11` | 17 | `0x040D` | `PICTURE` | `0x62` |
| `0x11` | 17 | `0x04A6` | `PICTURE` | `0x62` |
| `0x11` | 17 | `0x0E40` | `PICTURE` | `0x6B` |
| `0x11` | 17 | `0x21EE` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x034B` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x071F` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x088B` | `PICTURE` | `0x62` |
| `0x12` | 18 | `0x09C6` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x09EF` | `PICTURE` | `0x62` |
| `0x12` | 18 | `0x0A87` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x0B89` | `PICTURE` | `0x62` |
| `0x12` | 18 | `0x0C9C` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x0E31` | `PICTURE` | `0x50` |
| `0x12` | 18 | `0x0F2B` | `PICTURE` | `0x1D` |
| `0x12` | 18 | `0x0F9C` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x100E` | `PICTURE` | `0x1D` |
| `0x12` | 18 | `0x10A6` | `PICTURE` | `0x39` |
| `0x12` | 18 | `0x17CC` | `PICTURE` | `0x50` |
| `0x12` | 18 | `0x1B03` | `PICTURE` | `0x50` |
| `0x13` | 19 | `0x05E4` | `PICTURE` | `0x39` |
| `0x13` | 19 | `0x0A7A` | `PICTURE` | `0x65` |
| `0x13` | 19 | `0x0A9A` | `PICTURE` | `0x66` |
| `0x13` | 19 | `0x0ADA` | `PICTURE` | `0x66` |
| `0x13` | 19 | `0x0AFF` | `PICTURE` | `0x67` |
| `0x13` | 19 | `0x0BC9` | `PICTURE` | `0x68` |
| `0x13` | 19 | `0x0DE8` | `PICTURE` | `0x6F` |
| `0x13` | 19 | `0x11F9` | `PICTURE` | `0x60` |
| `0x13` | 19 | `0x1AAB` | `PICTURE` | `0x62` |
| `0x13` | 19 | `0x1B83` | `PICTURE` | `0x67` |
| `0x18` | 24 | `0x0128` | `PICTURE` | `0x1D` |
| `0x20` | 32 | `0x07B6` | `PICTURE` | `0x62` |
| `0x20` | 32 | `0x08D5` | `PICTURE` | `0x62` |
| `0x21` | 33 | `0x1F31` | `PICTURE` | `0x20` |
| `0x24` | 36 | `0x15B8` | `PICTURE` | `0x62` |
| `0x30` | 48 | `0x155A` | `PICTURE` | `0x38` |
| `0x30` | 48 | `0x16D6` | `PICTURE` | `0x6A` |
| `0x30` | 48 | `0x17BA` | `PICTURE` | `0x6A` |
| `0x30` | 48 | `0x1958` | `PICTURE` | `0x38` |
| `0x30` | 48 | `0x19D0` | `PICTURE` | `0x6A` |
| `0x30` | 48 | `0x20DC` | `PICTURE` | `0x54` |
| `0x31` | 49 | `0x1AD6` | `PICTURE` | `0x17` |
| `0x31` | 49 | `0x1D64` | `PICTURE` | `0x17` |
| `0x31` | 49 | `0x1E1D` | `PICTURE` | `0x17` |
| `0x32` | 50 | `0x045C` | `PICTURE` | `0x52` |
| `0x32` | 50 | `0x083F` | `PICTURE` | `0x37` |
| `0x32` | 50 | `0x0A4C` | `PICTURE` | `0x54` |
| `0x32` | 50 | `0x0ADF` | `PICTURE` | `0x37` |
| `0x32` | 50 | `0x144A` | `PICTURE` | `0x37` |
| `0x32` | 50 | `0x1603` | `PICTURE` | `0x37` |
| `0x32` | 50 | `0x1884` | `PICTURE` | `0x37` |
| `0x32` | 50 | `0x1AED` | `PICTURE` | `0x02` |
| `0x32` | 50 | `0x1BF2` | `PICTURE` | `0x02` |
| `0x32` | 50 | `0x1C9D` | `PICTURE` | `0x02` |
| `0x32` | 50 | `0x1F25` | `PICTURE` | `0x37` |
| `0x32` | 50 | `0x20B6` | `PICTURE` | `0x37` |
| `0x32` | 50 | `0x2154` | `PICTURE` | `0x37` |
| `0x40` | 64 | `0x0A71` | `PICTURE` | `0x6B` |
| `0x41` | 65 | `0x006C` | `PICTURE` | `0x02` |
| `0x41` | 65 | `0x0F3A` | `PICTURE` | `0x02` |
| `0x41` | 65 | `0x1142` | `PICTURE` | `0x62` |
| `0x42` | 66 | `0x08E4` | `PICTURE` | `0x1E` |
| `0x42` | 66 | `0x0A12` | `PICTURE` | `0x1E` |
| `0x50` | 80 | `0x01B7` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x05BC` | `PICTURE` | `0x1E` |
| `0x50` | 80 | `0x05CE` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x071E` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x0963` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x0A73` | `PICTURE` | `0x1E` |
| `0x50` | 80 | `0x0B27` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x0B58` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x0BB7` | `PICTURE` | `0x1E` |
| `0x50` | 80 | `0x0C6A` | `PICTURE` | `0x1E` |
| `0x50` | 80 | `0x0C6E` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x0CD7` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x0EF8` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x126C` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x1298` | `PICTURE` | `0x1D` |
| `0x50` | 80 | `0x12C3` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x13A1` | `PICTURE` | `0x1E` |
| `0x50` | 80 | `0x1580` | `PICTURE` | `0x62` |
| `0x50` | 80 | `0x15B8` | `PICTURE` | `0x62` |
| `0x50` | 80 | `0x1B6D` | `PICTURE` | `0x62` |
| `0x50` | 80 | `0x1C72` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x1CD0` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x1D5B` | `PICTURE` | `0x39` |
| `0x50` | 80 | `0x1F14` | `PICTURE` | `0x1D` |
| `0x50` | 80 | `0x2051` | `PICTURE` | `0x39` |
| `0x51` | 81 | `0x0CAD` | `PICTURE` | `0x1F` |
| `0x54` | 84 | `0x1455` | `PICTURE` | `0x1F` |
| `0x5F` | 95 | `0x0D22` | `PICTURE` | `0x62` |
| `0x60` | 96 | `0x04F5` | `PICTURE` | `0x1D` |
| `0x60` | 96 | `0x1190` | `PICTURE` | `0x1D` |
| `0x60` | 96 | `0x17E0` | `PICTURE` | `0x1D` |
| `0x61` | 97 | `0x0160` | `PICTURE` | `0x1D` |
| `0x61` | 97 | `0x06C9` | `PICTURE` | `0x1D` |
| `0x61` | 97 | `0x124F` | `PICTURE` | `0x1D` |
| `0x61` | 97 | `0x18CA` | `PICTURE` | `0x1D` |
| `0x62` | 98 | `0x0319` | `PICTURE` | `0x1D` |
| `0x62` | 98 | `0x0825` | `PICTURE` | `0x1D` |
| `0x62` | 98 | `0x1045` | `PICTURE` | `0x1D` |
| `0x62` | 98 | `0x16BB` | `PICTURE` | `0x1D` |
| `0x62` | 98 | `0x180D` | `PICTURE` | `0x1D` |
| `0x62` | 98 | `0x19A7` | `PICTURE` | `0x1D` |
| `0x62` | 98 | `0x1ADE` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x00BA` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x0161` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x06E6` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x0744` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x07F1` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x08A2` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x09A8` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x10F1` | `PICTURE` | `0x1D` |
| `0x70` | 112 | `0x2210` | `PICTURE` | `0x1D` |
| `0x71` | 113 | `0x1021` | `PICTURE` | `0x1D` |
| `0x71` | 113 | `0x1F42` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x062D` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x080C` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x08ED` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x091B` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x095D` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x09A3` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x0ADA` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x0C03` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x0D86` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x0E14` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x0F66` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x1017` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x1063` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x10B9` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x1118` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x116F` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x129D` | `PICTURE` | `0x1D` |
| `0x72` | 114 | `0x12C2` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x1389` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x14C7` | `PICTURE` | `0x04` |
| `0x72` | 114 | `0x154E` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x15A9` | `PICTURE` | `0x04` |
| `0x72` | 114 | `0x16B7` | `PICTURE` | `0x37` |
| `0x72` | 114 | `0x1F3C` | `PICTURE` | `0x20` |
| `0x72` | 114 | `0x2177` | `PICTURE` | `0x20` |

## The resources marked *not found*

`PICTURE` ids 80, 84, 96, 98, 101–104, 106, 107 and 111 are not in
`extracted/genesis_art/manifest.json`. They are not missing from the game —
they are the **VGADependentImages portraits**, the 173 recovered from
`PIC1` / `SPRIT1` / `PIC7` / `PIC8` by `tools/gbimage_vd.py`, which have
not been run through `tools/convert_art.py` yet. That conversion is the
first step of this work, not a separate problem.

`CPIC1` covers ids 1–192 but holds only 108 images, so a missing id there
is expected rather than a decode failure.

## Order of work

1. Convert the 173 VD portraits, so every id in the table above resolves.
2. Reverse the picture directory the way the ECL and GEO directories were
   reversed, and make it additive. `docs/re_notes.md` records the entry
   points: `PICTURE` dispatches to `0x03662`, which stores the id at
   `0xB525` and calls the loader at `0x04DFA`, which calls `0x092FC`.
3. Inject, then delete the id lists from `tools/artmap.py`. When both
   tuples there are empty the stopgap is gone.

## Creature sizes: what each engine draws

Measured, not inferred. Both numbers are the frame a creature occupies on
screen during combat, and both engines store 18 frames per creature.

**Genesis (Countdown).** The figure directory record at `0x9A14` is eight
bytes: a longword pointer, the figure id at `+4`, the sheet width in tiles
at `+5`, an animation-table index at `+6`, and a packed byte at `+7` whose
high nibble is the size class.

| class | sheet | frame | unique tiles | figures |
|---|---|---|---|---|
| 0 | 18 tiles wide | **24 x 24 px** | 81-146 | 43 |
| 2, 3 | 36 tiles wide | **24 x 48 px** | 161-219 | 9 |

The nine large ones are DESERT APE, HEXADILLO, SAND SQUID, LG. E.C. GENNIE,
RAM G.D. GENNIE, RAM ASSAULT BOT, RAM COMBAT BOT, ACID FROG and one unnamed
slot. So the engine's "big monster" is twice as **tall**, never wider.

Frames are read as a flat run of nametable cells, 9 cells for a small figure
and 18 for a large one, laid out row-major at 3 tiles wide. The sheet width
byte is only the atlas shape for the decompressor -- it is not the frame
shape. Rendering a sheet as if the two were the same is what made the first
previews look like scrambled body parts.

**DOS (Matrix Cubed).** `CPIC1.DAX` carries its size in the block header
(`byte 0` height, `byte 1` width in cells of 8):

| frame | count |
|---|---|
| 24 x 24 px | 82 |
| **48 x 24 px** | 16 |
| **48 x 48 px** | 10 |

DOS grows creatures **wider**, and its top class grows both ways. The ten
48 x 48 blocks are 18, 21, 22, 29, 32, 146, 149, 150, 157 and 160 --
blocks 22 and 157 are the dinosaur, in a standing and a lunging pose.

**So the classes do not line up.** A DOS 48 x 24 creature has no Genesis
class at all, and a DOS 48 x 48 creature is four times the area of the
Genesis standard against the large class's two. Converting the dinosaur
into the stock large class costs half its width.

Widening the Genesis class is a ROM change, not an art change: the width
byte at `+5` is a whole byte, so a 72-tile atlas encodes fine, but the code
that turns cells into a frame has a fixed 3-tile stride that has not been
found yet. Three routines read the record's `+6` and `+7` fields
(`0x0C3D2` class, `0x0CB48` animation, `0x0FBAE` geometry) and **none of
them has a caller anywhere in the ROM** -- no `bsr`, `jsr`, pc-relative
call or stored pointer. Whatever picks the frame stride is somewhere else.
That is the next thing to find, and until it is found the honest answer is
that the port supports 24 x 48 and no larger.

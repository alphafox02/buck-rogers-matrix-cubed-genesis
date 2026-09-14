# Buck Rogers: Matrix Cubed — Genesis

An attempt to answer one question:

> Can an authentic *Matrix Cubed* scenario be made to run correctly inside
> the Genesis *Countdown to Doomsday* engine?

Everything else depends on that result. The long-term goal is Matrix Cubed
as if SSI had shipped it for the Mega Drive / Genesis in 1992, with optional
32X and Sega CD enhancement much later.

See [`PROJECT_BRIEF_Matrix_Cubed_Genesis_32X.md`](PROJECT_BRIEF_Matrix_Cubed_Genesis_32X.md)
for the full plan and [`docs/devlog.md`](docs/devlog.md) for what has
actually happened.

## Status

| | |
|---|---|
| DAX container + compression | **solved** — 611/611 blocks |
| Gold Box VGA image format | **solved** — 3,430 images extracted |
| Genesis engine identified | **Gold Box ECL, 94 opcodes located** |
| ECL disassembler | not started |
| Genesis build loop | not started |

## Layout

```
docs/       findings, formats, development log
tools/      extraction and conversion tooling (Python 3)
reverse/    Genesis disassembly work
campaign/   converted scenario data
extracted/  generated output            (gitignored)
roms/       Genesis ROMs                (gitignored)
dos_game/   DOS Matrix Cubed files      (gitignored)
```

## Usage

```bash
# Verify the DAX reader against the game files
python3 tools/dax.py dos_game/matrix/*.DAX

# Extract every image to PNG
cd tools && python3 extract_images.py ../extracted/images ../dos_game/matrix/*.DAX
```

Requires Python 3 and Pillow.

## Legal

Use legitimately owned copies. **No commercial game data, ROMs, artwork or
extracted assets are committed to this repository** — see `.gitignore`.
This project produces tools and patches, not redistributable game content.

## Prior art

- [`farmboy0/ssi-engine`](https://gitlab.com/farmboy0/ssi-engine) — Gold Box
  engine reimplementation in Java. GPLv3. Read as documentation only.
- [`simeonpilgrim/goldboxexplorer`](https://github.com/simeonpilgrim/goldboxexplorer)
  and [`coab`](https://github.com/simeonpilgrim/coab) — the upstream source
  of most Gold Box format knowledge.
- [`viciious/d32xr`](https://github.com/viciious/d32xr) — reference for 32X
  dual-SH2 architecture, if we ever get there.

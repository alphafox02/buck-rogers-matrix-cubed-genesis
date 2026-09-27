# How this project happened

This is the narrative account: where the idea came from, how the approach was
arrived at, what turned out to be hard, and which habits earned their keep.
`docs/devlog.md` is the day-by-day record and `docs/re_notes.md` is the
reverse engineering itself. This file is the part that does not fit in either
— the reasoning, so that someone picking the project up knows not just what
was done but why it was done that way.

## Why this exists

I was the kid who rented the same game every single time.

Every trip to the video store, same cartridge: *Buck Rogers: Countdown to
Doomsday*. My sibling had to sit through it weekend after weekend while I
disappeared into it for hours. It is still a running joke between us, decades
later.

I am not entirely sure why that one stuck. It is slow, and it is mostly
reading, which is not what anyone bought a Genesis for. But I loved it, and I
never stopped wanting more of it.

So the first idea was the obvious one: maybe I could just make the sequel
myself. A new Buck Rogers game, picking up where that one left off.

Then I found out there already was a sequel. *Matrix Cubed* came out in 1992,
carries the story straight on from *Countdown*, and only ever shipped for DOS.
No console version, ever.

Which changed the question. Not "can I write a sequel", but **"can I give the
Genesis the sequel it should have had?"**

## The realisation that made it a software project

Wanting it and knowing how to get it are different problems, and at this point
I still assumed I would be *writing* a game, using the Genesis cartridge as a
reference for how one ought to look and feel.

Pulling that cartridge apart to learn from it is what changed my mind.

SSI's Gold Box engine was itself ported to the Genesis for *Countdown to
Doomsday* in 1991, and *Matrix Cubed* is built on the same engine. So the
cartridge already contains a working Gold Box engine: a tile renderer, a
tactical combat system, a sound driver, a script interpreter, a save system.
Everything a Buck Rogers game needs, running on the console, already written
and already debugged by the people who shipped it.

**The engine was not a reference. It was a target.** What it lacks is not
capability — it is the second game's content.

That is what turned an impossible project into a merely difficult one. And the
original idea is still there at the far end — once the tools can put *a*
campaign into this engine, there is no reason they could not put an original
one in too.

## The decision that made it feasible

The tempting approach is to port the DOS executable. That is a very large job
and it throws away the thing that makes this tractable: a Genesis engine
already exists and already works.

The approach taken instead, settled before any code was written, is a strict
division:

* **DOS *Matrix Cubed* is the content.** Story, maps, dialogue, event scripts,
  encounters, NPCs, enemies, items, mission flags, scripted sequences, music.
* **Genesis *Countdown to Doomsday* is the engine.** Controls, UI, the
  isometric view, tactical combat, the tile renderer, the sound driver.

Everything in `tools/` is a consequence of that split. The build reads the DOS
game for content, reads the Genesis cartridge for the engine, translates
between them, and writes a cartridge.

This worked because the two games are closer than they look. Both store
scripts as bytecode for the same virtual machine — the Genesis one added 32
opcodes but kept the numbering and the argument encoding. Both store maps in
essentially the same format. Cracking the Genesis script compression and the
DOS DAX archives early meant the rest of the project was translation rather
than invention.

## On using AI to do it

This was built with heavy AI assistance, and it seems worth being straight
about that rather than letting the commit log imply a lone reverse engineer.

It is genuinely good at this kind of work. Reading 68000, recognising that two
script formats are the same virtual machine with different numbering, grinding
through a compression scheme until the output stops being noise — that is
patient, detailed, unglamorous work, and there was far more of it here than
one person was going to get through alone.

It can also drive the game. `tools/play.py` runs a build under a scriptable
Genesis core, so a question like "does that door open?" gets answered by
walking into it and reading the coordinates back out of RAM, and most of the
behavioural claims in `docs/re_notes.md` were checked that way.

What it is not good at is judging whether its own answer is right. Left to
itself it will produce a confident, plausible, wrong explanation and move on,
and it did: the duplicate chancellor greeting got two complete and incorrect
accounts before the real cause turned up. Both were abandoned only because I
pushed back on them.

So the division of labour is not machine-reads / human-plays. It is closer to
this: the machine does the reading, the searching and a good deal of the
playing, and I decide what is worth looking at, notice when the result is
wrong, and refuse the first answer. Remove the steering and the
project produces confident nonsense at speed.

## The lesson the project kept relearning

If there is one thing to take from this repository, it is this:

> **Every id that crosses between the two games needs an explicit map. The
> engine almost never errors on a wrong id — it indexes off the end of a table
> and carries on.**

This was learned the hard way, repeatedly, in every resource space the project
touched:

* **Monsters.** *Matrix Cubed*'s 5 and 6 are PURGE COMMANDO and PURGE WARRIOR.
  *Countdown*'s are HEXADILLO and SAND SQUID. Passing ids through turned the
  prologue's fight with human supremacists into one with desert wildlife.
* **Skills.** The two games number their skills independently and have
  different numbers of them.
* **Pictures.** Two rounds of this. First the `PICTURE` opcode, then the
  discovery — much later, from a player's screenshot — that `SETUPMONSTERS`
  also takes a picture id in its *third* argument, so eight more portraits had
  been silently substituted for years of build history.
* **Wall codes.** Still outstanding. The per-square wall code is a second id
  space that was never mapped, so several of *Matrix Cubed*'s fifteen distinct
  walls collapse onto the same *Countdown* piece.
* **Ships.** *Matrix Cubed* numbers its ships from 1; the Genesis roster is
  0-based. Every space encounter was fought one slot too strong — a RAM MEDIUM
  arriving with a RAM HEAVY's stats, better than three times the player's ship.

The failure mode is always the same and always quiet. Nothing crashes. The
game simply does the wrong thing, plausibly, and you only find out by playing
it.

## Which is the other lesson

**Boot tests prove almost nothing. Playing it finds the real bugs.**

The project has a scriptable Genesis core (`tools/play.py`) that presses
buttons, reads RAM and captures frames, and it is genuinely valuable — most of
the behavioural claims in `docs/re_notes.md` were checked with it. But every
single one of the following was found by me playing the game and saying
something was wrong:

* the cargo elevator on the opening dock rendered as blocks of **letters and
  digits**, because two injectors had both been told a ROM address was free
  and the later one wrote over the first
* the chancellor greeting the party **twice** — once on arrival and again the
  first time they stepped back onto the square they started on
* launching from the port **looping back to the opening briefing** for ever,
  because the flag that says "the opening has happened" was never set
* a party boosted to level 12 **trapping the player in the training screen**,
  because the engine's experience tables stop at level 8
* enemy ships that could not be beaten, and a ship that could never break off
  an interception because its fuel counter started at zero

None of those would have been caught by a test that checks the ROM boots. The
habit that made them fixable was recording what the screenshot showed, then
going and finding the code, rather than guessing.

## The habits that paid off

**Every injector prints what it wrote, and the build checks for overlaps.**
`tools/romlayout.py` reads those reports back and fails the build if two
injectors wrote to the same place. It has caught real collisions three times.
It also *missed* one — the console art — because that tool's report line had
no matching pattern in the table, which is its own lesson: a check you have
not verified is a check you do not have.

**Free-space guards.** Every tool that writes a block of code into spare ROM
refuses if the destination is not actually empty. This has stopped several
patches from silently eating each other.

**The build is a pure function.** Delete the output, run it twice, get
byte-identical ROMs. Nothing is layered on anything previously extracted. This
makes bisecting possible, which is how several regressions were localised:
build with one step removed and see whether the symptom survives.

**Write down what was measured and what was guessed.** `docs/re_notes.md` is
long and deliberately distinguishes the two. Several times a note that said
"this is a guess, revisit if walls look wrong" turned out to be exactly the
thing that was wrong.

**Record the failures.** `tools/bigslide.py` is not used by the build. It
exists because seven measured attempts at one problem all failed, and the
header lists them so that an eighth attempt starts from the evidence rather
than from scratch.

## The interesting problems

**The cartridge fights back.** The ROM will not boot if a single byte changes:
there is an anti-tamper checksum. Finding and satisfying it was the gate that
had to be passed before anything else could be tried.

**A 48×48 creature.** The Genesis engine draws combat figures at 24×24, 24×48
and 48×24. *Matrix Cubed* has five creatures at 48×48, the Venus Dinosaur
among them. Adding a size class meant changing both renderers — a standing
figure is plane A tiles, a moving one is hardware sprites — and the Genesis
sprite hardware caps at 4×4 tiles, so a 48×48 creature cannot slide between
squares the way a smaller one does. It steps instead, and stays a whole
dinosaur the whole way.

**Music.** The DOS game's XMI files are converted to the Genesis sound
driver's own sequence format. The driver was reverse engineered far enough to
write to it directly.

**Text that does not fit.** The Genesis text window is four lines shorter than
the DOS one, so the transpiler re-paginates every string, simulating how the
engine's window will fill as it emits. Getting that wrong put dialogue on top
of itself.

**Things the port needs that neither game provides.** *Matrix Cubed* is Volume
II: it expects a party imported from *Countdown to Doomsday*, ship and all. It
therefore contains no pregenerated team and nothing that fuels a fresh ship.
The port has to supply both, which is why `tools/bootstub.py` exists and why
it sets story flags and ship systems as well as placing the party.

## Where it stands, and where to start

`README.md` has the current state. Broadly: the campaign transplants, the
opening plays, combat and space combat run, and the game is playable well past
the first level — but it has not been played to the end, and the way bugs have
been found so far strongly suggests more are waiting in the areas I have not
reached yet.

If you want to contribute, the most valuable thing is **to play it and report
precisely what you saw**. A screenshot with a sentence about what happened
just before has been worth more to this project than any amount of static
analysis.

If you want to work on the code, the outstanding items with the best
evidence-to-effort ratio are:

* **Wall codes** (`docs/re_notes.md`, "The dock's wall CODES were never
  mapped"). The measurement is done; what is missing is the correspondence
  between *Countdown*'s wall pieces and *Matrix Cubed*'s fifteen wall records.
* **Operand widths.** The transpiler emits every memory operand one byte wide,
  though DOS encodes the width in the type byte. 41 addresses are used two or
  four bytes wide. Fixing it needs `flagmap` to reserve room for wide
  variables first.
* **The walkable ports.** *Matrix Cubed* presents its ports as a menu; the
  Genesis engine can present them as places you walk around, and the opening
  dock already proves it. This is content work rather than reverse
  engineering.

The approach that has worked throughout: find the code before changing it,
measure rather than reason where you can, write down which of the two you did,
and let someone play it.

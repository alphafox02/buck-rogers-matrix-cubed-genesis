"""
Convert XMI to the Genesis driver's sequence format.

The driver understands four statuses and nothing else -- `0x8n` note off,
`0x9n` note on, `0xCn` program change, `0xFC` end -- and its dispatch at Z80
`0x08F2` is an infinite loop, so an unexpected status does not misbehave, it
hangs the machine. Anything XMI carries that is not one of those four is
dropped rather than translated: controllers, pitch bend, aftertouch.

Three things have to be narrowed:

  * **Velocity goes.** Events carry one data byte, so a note-on is just the
    note. Dynamics are lost; this is what the driver's own tracks do too.
  * **Delays become one byte.** A gap longer than 255 ticks is split by
    emitting a redundant program change for that channel, which the driver
    accepts and which changes nothing audible, carrying another 255 ticks.
  * **Note-offs become real.** XMI gives a note-on a duration; the parser
    already turns that into a separate note-off at the right time.

Running status is NOT used. Decoding the driver's own tracks shows every
single event carrying a full status byte -- 0 of roughly 1000 events in the
title theme and the menu theme omit one, including back to back repeats like
`93 42 01 93 47 09`. The Z80 expects three bytes per event and nothing else,
so emitting running status desynchronises it: it plays for about a second
and then wanders into whatever the misaligned bytes happen to mean.

Usage:
    xmi2seq.py <file.xmi> <song index> [out.bin]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xmi

MAX_DELTA = 0xFF
# The terminator is the PAIR 0xFC 0x80, and the 0x80 is what makes a track
# loop instead of stopping. Z80 0x08CB:
#
#     08CC: CP 0xFC
#     08CE: JR nz,0x08F2     ; any other 0xFx spins for ever
#     08D7: LD A,(IY)        ; the byte after 0xFC
#     08DA: CP 0x80
#     08DC: JR nz,0x08E9     ; -> (0x00EA)=1, the track stops
#     08DE: CALL 0x049A      ; else advance...
#     08E1: LD A,(0x00E2)
#     08E5: JR nz,0x08DE     ; ...until the ring pointer is page aligned
#     08E7: JR 0x0914        ; and go on reading events
#
# The skip lands on the page boundary the 68000 has just refilled with the
# track's own first bytes, because it wraps its ROM pointer back to the start
# at the same moment. So 0xFC 0x80 is the loop, and it only works if the
# region is a whole number of pages -- which tools/inject_music.py enforces.
END = bytes((0xFC, 0x80))
# The lead-in delay is read at Z80 0x0866 as `LD A,(IY) / AND A / JP m` --
# consumed only when it is positive. A value with bit 7 set is left in place
# and then parsed as a status byte, which desynchronises the whole track.
MAX_LEAD_IN = 0x7F
# A program change indexes the FM voice pointer table at 68k 0x1BAF4, which
# holds 44 entries -- and of those, SSI's fourteen tracks only ever name six:
# 1, 4, 6, 9, 10 and 11. General MIDI program numbers run to 127, and eight
# of the thirteen Matrix Cubed asks for (48, 58, 75, 84, 93, 112, 117, 122)
# are past the end of the table, so each one loaded a garbage pointer as a
# patch and turned that channel to noise until the next program change --
# music that comes and goes with static between.
#
# Fold the GM families onto the six voices that are known to sound.
VOICES = (1, 4, 6, 9, 10, 11)
GM_FAMILY = {
    0: 6,    # piano            -> the workhorse voice, 692 uses in stock
    1: 10,   # chromatic perc
    2: 9,    # organ
    3: 11,   # guitar
    4: 4,    # bass             -> the voice stock uses for its bass line
    5: 9,    # strings
    6: 9,    # ensemble
    7: 1,    # brass
    8: 1,    # reed
    9: 10,   # pipe
    10: 6,   # synth lead
    11: 9,   # synth pad
    12: 11,  # synth effects
    13: 10,  # ethnic
    14: 11,  # percussive
    15: 11,  # sound effects
}
DEFAULT_PATCH = 6


def _voice(program):
    """Map a General MIDI program onto a voice the driver actually has."""
    return GM_FAMILY.get(program // 8, DEFAULT_PATCH)

# Limits read off SSI's own tracks rather than guessed. Decoding the title
# theme at 0x0360D8 gives channels 1, 2, 3 and 9, notes 31 to 76, and never
# more than three notes sounding at once on a channel. Matrix Cubed's XMI
# uses seven channels, notes up to 94 and up to six at once, and handing the
# driver that produced music for a moment and then static -- it walks its
# frequency and voice tables off the end rather than clamping.
MELODIC = (1, 2, 3, 4)       # the FM channels SSI drives
PERCUSSION = 9
NOTE_LOW, NOTE_HIGH = 31, 76
MAX_VOICES = 3               # simultaneous notes per channel

# Percussion data bytes are NOT GM note numbers. SSI's tracks keep channel 9
# inside 36..41 in the title theme and 9..41 in the menu theme, while General
# MIDI puts drums at 35..81 -- so passing XMI's numbers through indexes off
# the end of whatever table the driver keeps. Fold the GM kit onto the six
# the title theme actually uses, which are known to sound.
DRUMS = {
    35: 36, 36: 36,                                    # bass drums
    37: 37, 39: 37,                                    # rim, clap
    38: 38, 40: 38,                                    # snares
    41: 39, 43: 39, 45: 39, 47: 39, 48: 39, 50: 39,    # toms
    42: 40, 44: 40,                                    # closed hats
    46: 41, 49: 41, 51: 41, 52: 41, 53: 41,            # open hat, cymbals
    55: 41, 57: 41, 59: 41,
}
DRUM_DEFAULT = 40


def _fold(note):
    """Bring a note into the driver's range an octave at a time."""
    while note > NOTE_HIGH:
        note -= 12
    while note < NOTE_LOW:
        note += 12
    return note


def _remap(chan):
    """Fold the extra melodic channels onto the ones SSI drives."""
    if chan == PERCUSSION:
        return PERCUSSION
    return MELODIC[(chan - 1) % len(MELODIC)]


def convert(events, scale=1.0):
    """Return the driver's byte stream for one song."""
    patch = {}
    out = bytearray()
    # A track opens with its lead-in delay.
    first = int(events[0][0] * scale) if events else 0
    out.append(min(first, MAX_LEAD_IN))

    pending = []
    live = {}                              # notes sounding per channel
    for t, st, data in events:
        kind = st & 0xF0
        chan = _remap(st & 0x0F)
        if kind == 0xC0:
            voice = _voice(data[0])
            if patch.get(chan) == voice:
                continue                   # the fold makes these repeat
            patch[chan] = voice
            pending.append((int(t * scale), 0xC0 | chan, voice))
            continue
        if kind not in (0x80, 0x90):
            continue                       # the driver would hang on it
        note = (DRUMS.get(data[0], DRUM_DEFAULT) if chan == PERCUSSION
                else _fold(data[0]))
        held = live.setdefault(chan, [])
        if kind == 0x90:
            if len(held) >= MAX_VOICES:
                continue                   # more than the driver can sound
            held.append(note)
        else:
            if note not in held:
                continue                   # its note-on was dropped
            held.remove(note)
        pending.append((int(t * scale), kind | chan, note))

    for i, (t, st, note) in enumerate(pending):
        nxt = pending[i + 1][0] if i + 1 < len(pending) else t
        gap = max(0, nxt - t)
        # Three bytes, always: status, data, delay. No running status.
        out += bytes((st, note))
        # Split a gap no single byte can hold, using a harmless repeat of the
        # channel's own program change to carry the extra time.
        while gap > MAX_DELTA:
            chan = st & 0x0F
            out += bytes((MAX_DELTA, 0xC0 | chan, patch.get(chan, DEFAULT_PATCH)))
            gap -= MAX_DELTA
        out.append(gap)
    out += END
    return bytes(out)


if __name__ == "__main__":
    data = Path(sys.argv[1]).read_bytes()
    index = int(sys.argv[2], 0)
    got = xmi.songs(data)
    if index >= len(got):
        sys.exit(f"{Path(sys.argv[1]).name} has {len(got)} songs")
    b, e = got[index]
    ev = xmi.events(data, b, e)
    seq = convert(ev)
    print(f"song {index}: {len(ev)} events -> {len(seq)} bytes")
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_bytes(seq)
        print(f"wrote {sys.argv[3]}")

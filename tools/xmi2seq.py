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

Running status is used wherever the status byte repeats, which is what the
driver's own data does and keeps tracks compact.

Usage:
    xmi2seq.py <file.xmi> <song index> [out.bin]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import xmi

MAX_DELTA = 0xFF
END = 0xFC
DEFAULT_PATCH = 0

# Limits read off SSI's own tracks rather than guessed. Decoding the title
# theme at 0x0360D8 gives channels 1, 2, 3 and 9, notes 31 to 76, and never
# more than three notes sounding at once on a channel. Matrix Cubed's XMI
# uses seven channels, notes up to 94 and up to six at once, and handing the
# driver that produced music for a moment and then static -- it walks its
# frequency and voice tables off the end rather than clamping.
MELODIC = (1, 2, 3)          # the FM channels SSI drives
PERCUSSION = 9
NOTE_LOW, NOTE_HIGH = 31, 76
MAX_VOICES = 3               # simultaneous notes per channel


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
    out.append(min(first, MAX_DELTA))

    status = None
    pending = []
    live = {}                              # notes sounding per channel
    for t, st, data in events:
        kind = st & 0xF0
        chan = _remap(st & 0x0F)
        if kind == 0xC0:
            if patch.get(chan) == data[0]:
                continue                   # the fold makes these repeat
            patch[chan] = data[0]
            pending.append((int(t * scale), 0xC0 | chan, data[0]))
            continue
        if kind not in (0x80, 0x90):
            continue                       # the driver would hang on it
        note = data[0] if chan == PERCUSSION else _fold(data[0])
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
        if st != status:
            out.append(st)
            status = st
        out.append(note)
        # Split a gap no single byte can hold, using a harmless repeat of the
        # channel's own program change to carry the extra time.
        while gap > MAX_DELTA:
            out.append(MAX_DELTA)
            chan = st & 0x0F
            out.append(0xC0 | chan)
            out.append(patch.get(chan, DEFAULT_PATCH))
            status = 0xC0 | chan
            gap -= MAX_DELTA
        out.append(gap)
    out.append(END)
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

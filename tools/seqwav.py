# SPDX-License-Identifier: MIT
"""
Render music to a WAV so it can be judged by ear without a MIDI player.

Two inputs, deliberately:

    --xmi <file> <song>     the DOS original, every channel and every note
    --seq <file>            a Genesis stream, parsed exactly as the Z80 does

Playing both tells you whether a bad result is the conversion throwing away
something it should have kept, or the driver being fed something it cannot
read. Neither is FM synthesis -- this is a plain square-wave voice with a
short decay -- so it is for recognising the tune and its timing, not for
judging the timbre.

Usage:
    seqwav.py --xmi dos_game/matrix/BUCKA.XMI 0 out.wav
    seqwav.py --seq track.bin out.wav [ticks_per_second]
"""

import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RATE = 22050
# The driver counts its delay bytes off a fixed timer. 120 a second puts the
# stock title theme's 2258 units at about nineteen seconds, which is the
# right order for a Genesis loop.
TICKS = 120.0
DECAY = 0.9         # seconds for a note to fall silent


def freq(note):
    return 440.0 * 2 ** ((note - 69) / 12.0)


def render(notes, seconds):
    """notes: (start_seconds, duration_seconds, midi_note, is_drum)"""
    n = int(seconds * RATE) + RATE
    buf = [0.0] * n
    for t0, dur, note, drum in notes:
        i0 = int(t0 * RATE)
        length = int(min(dur, DECAY) * RATE)
        if drum:
            # Noise burst, pitched by note number.
            seed = 0x1234 + note
            for k in range(min(length, int(0.08 * RATE))):
                seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                env = 1.0 - k / (0.08 * RATE)
                if i0 + k < n:
                    buf[i0 + k] += ((seed >> 16 & 1) * 2 - 1) * 0.25 * env * env
            continue
        step = freq(note) / RATE
        phase = 0.0
        for k in range(length):
            phase += step
            env = math.exp(-3.0 * k / RATE)
            if i0 + k < n:
                buf[i0 + k] += (1.0 if phase % 1.0 < 0.5 else -1.0) * 0.18 * env
    peak = max(1.0, max(abs(v) for v in buf) if buf else 1.0)
    return b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v / peak)) * 32000))
                    for v in buf)


def from_xmi(path, song):
    import xmi
    data = Path(path).read_bytes()
    b, e = xmi.songs(data)[song]
    events = xmi.events(data, b, e)
    # XMI carries its own tick rate; SSI's files run at 120 a second.
    live, notes = {}, []
    for t, st, args in events:
        kind, chan = st & 0xF0, st & 0x0F
        if kind == 0x90:
            live[(chan, args[0])] = t
        elif kind == 0x80 and (chan, args[0]) in live:
            t0 = live.pop((chan, args[0]))
            notes.append((t0 / TICKS, (t - t0) / TICKS, args[0], chan == 9))
    end = max((t0 + d for t0, d, _, _ in notes), default=1.0)
    return notes, end


def from_seq(path):
    """Parse a Genesis stream the way the Z80's dispatch at 0x087D does."""
    buf = Path(path).read_bytes()
    i, now = 1, buf[0]
    live, notes = {}, []
    while i + 2 < len(buf):
        st = buf[i]
        if st == 0xFC:
            break
        if st < 0x80:
            raise SystemExit(f"desync: 0x{st:02X} where a status byte belongs, at 0x{i:X}")
        kind, chan, data, delay = st & 0xF0, st & 0x0F, buf[i + 1], buf[i + 2]
        if kind == 0x90:
            live[(chan, data)] = now
        elif kind == 0x80 and (chan, data) in live:
            t0 = live.pop((chan, data))
            notes.append((t0 / TICKS, (now - t0) / TICKS, data, chan == 9))
        now += delay
        i += 3
    end = max((t0 + d for t0, d, _, _ in notes), default=1.0)
    return notes, end


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == "--xmi":
        notes, end = from_xmi(sys.argv[2], int(sys.argv[3], 0))
        out = sys.argv[4]
    elif sys.argv[1] == "--seq":
        notes, end = from_seq(sys.argv[2])
        out = sys.argv[3]
    else:
        sys.exit(__doc__)
    pcm = render(notes, end)
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(pcm)
    print(f"{len(notes)} notes, {end:.1f}s -> {out}")

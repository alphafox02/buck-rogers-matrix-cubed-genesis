"""
Decode a track for the SHayes1991 sound driver.

The driver is MIDI-shaped. Its dispatch at Z80 0x087D switches on the top
nibble of a status byte and takes the channel from the low nibble:

    087E: AND 0xF0
    0880: CP 0x80     note off
    089F: CP 0x90     note on
    08AE: CP 0xC0     program change
    08C7: CP 0xF0 / 0xFC   end of track
    088E: AND 15      channel

Running status is the MIDI convention exactly -- a byte with bit 7 clear
reuses the previous status:

    0960: LD A,(IY)
    0964: JP m,0x096c      ; bit 7 set: new status
    0967: LD A,(0x00E7)    ; else reuse
    0973: LD (0x00E7),A

and every handler returns through 0x0914, which reads **one delta byte**
into the tick countdown at 0x00E8. Channel 9 is percussion, keyed by
General MIDI note numbers (0x24 bass drum, 0x26 snare, 0x31 crash).

So a track is: 24-byte header, then `status, data..., delta` repeated, with
running status. The 68000 copies the header to Z80 RAM at 0xA0003A before
starting playback (0x1B8DC).

Usage:
    seqdec.py <rom> <track offset> [events]
"""

import sys
from pathlib import Path

# No header: the music table at 0x1BAC0 points straight at the event stream.
HEADER = 0

NAMES = {0x80: "note_off", 0x90: "note_on", 0xA0: "aftertouch",
         0xB0: "control", 0xC0: "program", 0xD0: "pressure", 0xE0: "bend"}
# ONE data byte per event, not MIDI's two: note on and note off carry a note
# and no velocity. The handler at 0x088D reads a single byte --
# `LD D,(IY)` then `CALL 0x049A` -- and nothing else.
DATA_BYTES = {0x80: 1, 0x90: 1, 0xA0: 1, 0xB0: 1, 0xC0: 1, 0xD0: 1, 0xE0: 1}


def decode(rom, at, limit=64):
    p = at + HEADER
    # A stream opens with a delta, then runs status/data/delta.
    lead = rom[p]
    p += 1
    out = [(p, None, [], lead, "lead-in delay")]
    status = None
    while len(out) < limit:
        b = rom[p]
        if b & 0x80:
            if b == 0xFC:
                out.append((p, 0xFC, [], None, "end_of_track"))
                break
            status, p = b, p + 1
        elif status is None:
            return out, "no running status to reuse"
        kind = status & 0xF0
        chan = status & 0x0F
        n = DATA_BYTES.get(kind)
        if n is None:
            return out, f"unknown status 0x{status:02X} at 0x{p:05X}"
        data = list(rom[p:p + n])
        p += n
        delta = rom[p]
        p += 1
        out.append((p, status, data, delta, NAMES.get(kind, "?")))
    return out, None


if __name__ == "__main__":
    rom = Path(sys.argv[1]).read_bytes()
    at = int(sys.argv[2], 0)
    limit = int(sys.argv[3], 0) if len(sys.argv) > 3 else 40
    events, err = decode(rom, at, limit)
    print(f"track 0x{at:05X}: header {rom[at:at+HEADER].hex()}")
    for p, status, data, delta, name in events:
        if status is None:
            print(f"  --       {name:<14}        delta {delta}")
            continue
        ch = status & 0x0F
        d = " ".join(f"{x:02X}" for x in data)
        extra = ""
        if name in ("note_on", "note_off") and data:
            n = data[0]
            octave, step = divmod(n, 12)
            extra = f"  {'C C#D D#E F F#G G#A A#B '[step*2:step*2+2].strip()}{octave - 1}"
            if ch == 9:
                extra = "  (percussion)"
        print(f"  {status:02X} ch{ch:<2} {name:<12} {d:<4} delta {delta:<4}{extra}")
    if err:
        print(f"  STOPPED: {err}")

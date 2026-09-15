"""
Export a Genesis music track as a standard MIDI file.

Proof that the format in docs/re_notes.md is right: if the decode is
correct these play as music, and if it is wrong they do not.

The driver's streams are MIDI with one data byte per event and a delta after
each, so going out to a .mid is mostly re-widening what was narrowed:
restore a velocity, convert the one-byte delta to a variable-length
quantity, and keep the channel as it is. Channel 9 is already General MIDI
percussion.

Usage:
    seq2mid.py <rom> <track offset> <out.mid> [events]
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import seqdec

VELOCITY = 100
TICKS_PER_BEAT = 24      # the driver's delta is in ticks; 24 reads musically


def vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def build(rom, at, limit):
    events, err = seqdec.decode(rom, at, limit)
    track = bytearray()
    pending = 0
    for _, status, data, delta, name in events:
        if status is None:                      # the lead-in delay
            pending += delta or 0
            continue
        if name == "end_of_track":
            break
        kind = status & 0xF0
        track += vlq(pending)
        pending = delta or 0
        if kind in (0x80, 0x90):
            track += bytes([status, data[0], 0 if kind == 0x80 else VELOCITY])
        else:
            track += bytes([status] + data)
    track += vlq(pending) + b"\xff\x2f\x00"
    head = b"MThd" + struct.pack(">IHHH", 6, 0, 1, TICKS_PER_BEAT)
    return head + b"MTrk" + struct.pack(">I", len(track)) + bytes(track), err


if __name__ == "__main__":
    rom = Path(sys.argv[1]).read_bytes()
    at = int(sys.argv[2], 0)
    out = Path(sys.argv[3])
    limit = int(sys.argv[4], 0) if len(sys.argv) > 4 else 20000
    data, err = build(rom, at, limit)
    out.write_bytes(data)
    print(f"wrote {out} ({len(data)} bytes)" + (f"; decode stopped: {err}" if err else ""))

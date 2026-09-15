"""
Parse XMI (Extended MIDI), the format DOS Matrix Cubed's music is in.

XMI is IFF: a FORM XDIR giving the song count, then a CAT XMID holding one
FORM XMID per song, each with a TIMB patch list and an EVNT event stream.

It differs from a .mid in two ways that matter here:

  * Delays are a run of bytes below 0x80. Each contributes its value, and a
    byte below 0x7F ends the run, so 0x7F means "127 and keep going".
  * There are no note-off events. A note-on carries a variable-length
    DURATION after its velocity, and the player schedules the release.

Both differences disappear on the way out: the Genesis driver wants
absolute-ordered events with a one-byte delta, so durations become real
note-offs and the runs become plain numbers.
"""

import struct


def _chunks(data, at, end):
    while at + 8 <= end:
        tag = data[at:at + 4]
        size = struct.unpack_from(">I", data, at + 4)[0]
        body = at + 8
        yield tag, body, body + size
        at = body + size + (size & 1)


def songs(data):
    """Every EVNT stream in the file, in order."""
    out = []
    for tag, body, end in _chunks(data, 0, len(data)):
        if tag == b"CAT " and data[body:body + 4] == b"XMID":
            for t2, b2, e2 in _chunks(data, body + 4, end):
                if t2 == b"FORM" and data[b2:b2 + 4] == b"XMID":
                    for t3, b3, e3 in _chunks(data, b2 + 4, e2):
                        if t3 == b"EVNT":
                            out.append((b3, e3))
    return out


def _vlq(data, at):
    n = 0
    while True:
        b = data[at]
        at += 1
        n = (n << 7) | (b & 0x7F)
        if not b & 0x80:
            return n, at


def events(data, at, end):
    """(time, status, data bytes) with note-offs made explicit."""
    out = []
    now = 0
    while at < end:
        b = data[at]
        if b < 0x80:                      # a delay run
            while at < end and data[at] < 0x80:
                v = data[at]
                at += 1
                now += v
                if v < 0x7F:
                    break
            continue
        status = b
        at += 1
        kind = status & 0xF0
        if status == 0xFF:                # meta
            meta = data[at]
            at += 1
            n, at = _vlq(data, at)
            at += n
            continue
        if kind == 0xC0 or kind == 0xD0:
            out.append((now, status, [data[at]]))
            at += 1
        elif kind == 0x90:
            note, vel = data[at], data[at + 1]
            at += 2
            dur, at = _vlq(data, at)
            out.append((now, status, [note, vel]))
            out.append((now + dur, 0x80 | (status & 0x0F), [note, 0]))
        else:
            out.append((now, status, [data[at], data[at + 1]]))
            at += 2
    out.sort(key=lambda e: e[0])
    return out

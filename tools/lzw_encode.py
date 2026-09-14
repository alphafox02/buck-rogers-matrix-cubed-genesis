"""
Compressor for the Genesis ECL streams -- the inverse of the decoder in
tools/genesis_ecl.py.

The emit rule is derived directly from the reader at 0x0A092. That routine
takes the top `width - 1` bits as a candidate value and then:

    value > thresh  ->  the code IS that value, and only width-1 bits were
                        consumed
    value <= thresh ->  one more bit is consumed and, if set, 0x100 (more
                        generally 1 << (width-1)) is added

So to emit a code C, split it into a low part and a high bit:

    low  = C & ((1 << (width-1)) - 1)
    high = C >> (width-1)

  * If high is set, the decoder must be made to read the extra bit, which
    requires low <= thresh. That always holds: thresh is `next - 0x100` and
    C < next, so low < thresh.
  * If high is clear and low > thresh, emit low in width-1 bits and stop --
    the decoder will read no further.
  * If high is clear and low <= thresh, the value is ambiguous, so emit
    width-1 bits followed by a 0 bit to disambiguate.

Bits go out most-significant first, matching how the reader fills its
32-bit accumulator a byte at a time.

One subtlety dominates correctness: the decoder creates each dictionary
entry one code LATER than the encoder does, because it needs the following
code before it knows the entry's final byte. Its `next`/`thresh`/`width`
therefore lag the encoder's by a single step, and codes must be emitted
using the DECODER's state or the two desynchronise the moment a width
boundary is crossed. This encoder tracks that lagged state explicitly.
"""

CLEAR, END = 0x100, 0x101


class _Writer:
    def __init__(self):
        self.bits = bytearray()

    def put(self, value, count):
        for i in range(count - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def bytes(self):
        out = bytearray()
        padded = self.bits + bytearray((-len(self.bits)) % 8)
        for i in range(0, len(padded), 8):
            byte = 0
            for bit in padded[i:i + 8]:
                byte = (byte << 1) | bit
            out.append(byte)
        return bytes(out)


def _emit(writer, code, width, thresh):
    half = width - 1
    low = code & ((1 << half) - 1)
    high = code >> half
    if high:
        writer.put(low, half)
        writer.put(1, 1)
    elif low > thresh:
        writer.put(low, half)
    else:
        writer.put(low, half)
        writer.put(0, 1)


def _codes(data: bytes):
    """Produce the code sequence, assigning dictionary indices as the
    decoder will assign them."""
    table = {bytes([i]): i for i in range(256)}
    nxt, top, width = 0x102, 0x1FF, 9
    out = []
    current = b""
    for byte in data:
        candidate = current + bytes([byte])
        if candidate in table:
            current = candidate
            continue
        out.append(table[current])
        if nxt <= top:
            table[candidate] = nxt
            nxt += 1
            if nxt == top and width < 12:
                width += 1
                top = (1 << width) - 1
        current = bytes([byte])
    if current:
        out.append(table[current])
    return out


def compress(data: bytes) -> bytes:
    writer = _Writer()
    # Mirror of the DECODER's state, which lags entry creation by one code.
    width, nxt, thresh, top = 9, 0x102, 2, 0x1FF

    for index, code in enumerate(_codes(data) + [END]):
        _emit(writer, code, width, thresh)
        # The decoder adds an entry after every code but the first.
        if index >= 1 and nxt <= top:
            nxt += 1
            thresh = (thresh + 1) & 0xFFFF
            if nxt == top and width < 12:
                width += 1
                top = (1 << width) - 1
                thresh = 0xFFFF
    return writer.bytes()

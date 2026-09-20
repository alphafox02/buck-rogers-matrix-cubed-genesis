"""
Drive the DOS original under DOSBox, to compare it against the port.

Screenshots from a person were the only ground truth this project had for
anything the DOS game does, which made every question cost a round trip.
This drives Matrix Cubed itself: it sends real keystrokes through X11's
XTEST extension and reads the window back, so "where does de Sade actually
meet you" can be answered by walking there.

    from dosdrive import find, focus, key, shot
    w = find(); focus(w)
    key("Up"); shot(w, "where.png")

Needs python-xlib, which is not a build dependency -- put it in a venv:

    python3 -m venv /tmp/xvenv && /tmp/xvenv/bin/pip install python-xlib pillow

Controls differ between the two games and it matters when comparing:

    DOS        relative -- Up walks forward, KP_Left/KP_Right turn in place
    Genesis    absolute -- the d-pad walks in compass directions

so to face a wall in DOS you turn, and in the port you have to ARRIVE
travelling that way.

The status line gives DOS's own coordinates and facing -- "11,5 W 00:14" --
which is what let every square be checked against the port's RAM.
"""
import time

from Xlib import X, XK, display
from Xlib.ext import xtest
from PIL import Image

_d = display.Display()
_root = _d.screen().root


def find(name="DOSBox"):
    """The DOSBox window, or None."""
    def walk(w):
        try:
            n = w.get_wm_name()
        except Exception:
            n = None
        if n and name.lower() in n.lower():
            g = w.get_geometry()
            if g.width > 200 and g.height > 150:
                return w
        for c in w.query_tree().children:
            r = walk(c)
            if r:
                return r
        return None
    return walk(_root)


def focus(w):
    w.set_input_focus(X.RevertToParent, X.CurrentTime)
    w.configure(stack_mode=X.Above)
    _d.sync()
    time.sleep(0.25)


def key(name, hold=0.06, rest=0.4, count=1):
    """Press a key by X keysym name: Return, Up, KP_Right, Escape, a, 1..."""
    ks = XK.string_to_keysym(name) if len(name) > 1 else ord(name)
    code = _d.keysym_to_keycode(ks)
    for _ in range(count):
        xtest.fake_input(_d, X.KeyPress, code)
        _d.sync()
        time.sleep(hold)
        xtest.fake_input(_d, X.KeyRelease, code)
        _d.sync()
        time.sleep(rest)


def shot(w, path=None):
    """Grab the window. DOSBox renders 640x400 for this game."""
    g = w.get_geometry()
    raw = w.get_image(0, 0, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
    im = Image.frombytes("RGB", (g.width, g.height), raw.data, "raw", "BGRX")
    if path:
        im.save(path)
    return im


def highlighted_row(w, first=38, step=16, rows=14):
    """Which menu row is highlighted -- inverse video reads as a bright bar.

    Counting keypresses to reach a menu item does not survive the menus
    wrapping; reading the highlight does.
    """
    import numpy as np
    a = np.asarray(shot(w).convert("L")).astype(int)
    best, bv = 0, -1.0
    for i in range(rows):
        y = first + i * step
        if y + step > a.shape[0]:
            break
        v = float(a[y:y + step, 20:620].mean())
        if v > bv:
            best, bv = i, v
    return best, bv

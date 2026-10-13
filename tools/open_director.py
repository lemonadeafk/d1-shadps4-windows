"""From orbit: dismiss the arrival popups (their number varies), open the Director, hover the Tower.

    python tools\\open_director.py [out.png]

Popups are detected from a background screenshot (a dark band across the middle of the screen), so
this presses X only while one is showing. Then it steers the free cursor onto SET DESTINATION
(left stick = A/S holds from the screen centre), presses X, and nudges the cursor so the Tower's
hover card appears. Replaces open_director.sh.
"""
import os
import sys
import tempfile
import time

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamewin  # noqa: E402
import cursor  # noqa: E402


def shot():
    p = os.path.join(tempfile.gettempdir(), "d1_od.png")
    gamewin.shot_bg(p)
    return Image.open(p).convert("RGB")


def popup_showing(im):
    # every orbit popup has a full-width near-black prompt bar ("X OK") somewhere in the lower half;
    # open orbit is sky/planet there. (A row through the popup body crosses its text - don't use it.)
    w, h = im.size
    xs = [int(w * f) for f in (0.08, 0.3, 0.7, 0.92)]
    return any(all(max(im.getpixel((x, y))) < 12 for x in xs) for y in range(int(h * 0.65), int(h * 0.92), 2))


def director_open(im):
    # the Director is a near-black star chart; orbit is a bright planet limb
    w, h = im.size
    pts = [im.getpixel((int(w * fx), int(h * fy))) for fx in (0.1, 0.3, 0.5, 0.7, 0.9) for fy in (0.12, 0.5)]
    return sum(max(p) for p in pts) / len(pts) < 70


def wait_for(pred, timeout, every=0.2):
    """Poll background screenshots until pred(image) is true; False on timeout."""
    end = time.time() + timeout
    while time.time() < end:
        if pred(shot()):
            return True
        time.sleep(every)
    return False


def settle(timeout=8.0, quiet=0.45, tol=2.0, first=0.5):
    """Wait until the picture stops changing (a screen transition has finished)."""
    import numpy as np
    time.sleep(first)                           # the transition has to start first
    prev, since, end = None, None, time.time() + timeout
    while time.time() < end:
        im = np.asarray(shot().convert("L").resize((160, 90)), dtype=np.int16)
        if prev is not None and np.abs(im - prev).mean() < tol:
            since = since or time.time()
            if time.time() - since >= quiet:
                return True
        else:
            since = None
        prev = im
        time.sleep(0.12)
    return False


def main(out=None):
    # The arrival popups (their number varies): press X the moment one is showing; done once
    # none has shown for a second. (This used to wait 2.5 s after every press.)
    clear_since, end = None, time.time() + 45
    while time.time() < end:
        if popup_showing(shot()):
            gamewin.tap("n")
            clear_since = None
            time.sleep(0.3)
        else:
            clear_since = clear_since or time.time()
            if time.time() - clear_since > 1.0:
                break
            time.sleep(0.12)
    else:
        raise SystemExit("popups never cleared")
    for attempt in range(3):
        cursor.steer(190, 540, log=print)       # SET DESTINATION (bottom left)
        gamewin.tap("n")
        if wait_for(director_open, 8):
            break
        print("Director did not open; retrying")
    else:
        raise SystemExit("could not open the Director")
    time.sleep(0.6)                             # the star chart is still sliding in
    gamewin.hold(["s"], 0.04)
    time.sleep(0.4)
    if out:
        print(gamewin.shot_bg(out))


if __name__ == "__main__":
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
    main(sys.argv[1] if len(sys.argv) > 1 else None)

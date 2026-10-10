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


def main(out=None):
    for _ in range(10):
        if not popup_showing(shot()):
            break
        gamewin.key("n")
        time.sleep(2.5)
    else:
        raise SystemExit("popups never cleared")
    time.sleep(1.0)
    for attempt in range(3):
        cursor.steer(190, 540, log=print)       # SET DESTINATION (bottom left)
        gamewin.key("n")
        time.sleep(6)
        if director_open(shot()):
            break
        print("Director did not open; retrying")
    else:
        raise SystemExit("could not open the Director")
    gamewin.hold(["s"], 0.04)
    time.sleep(0.8)
    if out:
        print(gamewin.shot_bg(out))


if __name__ == "__main__":
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
    main(sys.argv[1] if len(sys.argv) > 1 else None)

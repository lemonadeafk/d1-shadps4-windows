r"""Find the Destiny free cursor (a pale CLOSED ring, 26 px radius, flat and darker inside) in a game screenshot.

    python tools\cursor.py shot.png      -> prints "x y score"

Ring score at a candidate centre = the DARKEST point on the r=26 circle minus the mean brightness
inside (r=16) and outside (r=40): only a complete ring of that exact radius scores high, which
rejects text edges and the other circles on screen (measured profile: 13 inside, 115 on the ring). Used by the closed-loop steering in open_director.py / launch_tower.py.
"""
import math
import sys

from PIL import Image

R = 26


def _offsets(radius, n=40):
    return [(round(radius * math.cos(2 * math.pi * k / n)), round(radius * math.sin(2 * math.pi * k / n)))
            for k in range(n)]


RING, INNER, OUTER = _offsets(R), _offsets(R - 10, 24), _offsets(R + 14, 24)


def find(im):
    """(x, y, score) of the best ring candidate. Vectorised: every pixel is scored at once
    (the first version walked the image in Python and took seconds per frame)."""
    import numpy as np
    g = np.asarray(im.convert("L"), dtype=np.int16)
    h, w = g.shape
    pad = R + 14
    ring_src = np.pad(g, pad, constant_values=255)      # outside the screen never lowers the minimum
    val_src = np.pad(g, pad, constant_values=0)
    inside = np.pad(np.ones_like(g), pad, constant_values=0)

    def window(src, dx, dy):
        return src[pad + dy:pad + dy + h, pad + dx:pad + dx + w]

    ring_min = np.full((h, w), 255, dtype=np.int16)
    ring_n = np.zeros((h, w), dtype=np.int16)
    for dx, dy in RING:
        np.minimum(ring_min, window(ring_src, dx, dy), out=ring_min)
        ring_n += window(inside, dx, dy)
    ring_min[ring_n < len(RING) * 0.55] = 0             # the ring may be clipped by a screen edge
    total = np.zeros((h, w), dtype=np.int32)
    count = np.zeros((h, w), dtype=np.int32)
    for dx, dy in INNER:
        total += window(val_src, dx, dy)
        count += window(inside, dx, dy)
    score = ring_min - total / np.maximum(count, 1)      # the interior is always darker than the ring
    y, x = np.unravel_index(int(np.argmax(score)), score.shape)
    return int(x), int(y), float(score[y, x])


if __name__ == "__main__":
    print(*find(Image.open(sys.argv[1])))


def steer(tx, ty, tol=22, tries=18, log=None):
    """Move the free cursor to (tx, ty) in client pixels (1280x720 layout), closed loop.

    Returns True when the cursor is within `tol` px, or has vanished near the target (it snaps onto
    buttons and changes shape there). Left stick = W/A/S/D; hold time is proportional to distance.
    Long horizontal trips go through the empty middle band of the screen (y ~ 300): the bottom
    edge holds SET DESTINATION, the destination title and LAUNCH, all of which grab or hide the
    cursor. If it vanishes away from the target it is pushed UP out of whatever it is over.
    """
    import os
    import tempfile
    import time

    import gamewin
    path = os.path.join(tempfile.gettempdir(), "d1_steer.png")
    last, lost = None, 0
    for _ in range(tries):
        gamewin.shot_bg(path)
        im = Image.open(path)
        sx, sy = im.size[0] / 1280.0, im.size[1] / 720.0
        x, y, score = find(im)
        x, y = x / sx, y / sy
        if score < 25:
            near = last is not None and abs(last[0] - tx) < 130 and abs(last[1] - ty) < 100
            if log:
                log(f"cursor not visible (score {score:.0f}); last seen {last}; near target: {near}")
            if near:
                return True
            lost += 1
            if lost <= 3:
                gamewin.hold(["w"], 0.3)        # climb out of the bottom-edge widgets
            else:
                gamewin.hold(["a", "w"], 1.6)   # pin to the empty top-left corner...
                gamewin.hold(["d", "s"], 0.12)  # ...then step back inside so the ring is whole
                lost = 0
            time.sleep(0.5)
            continue
        lost = 0
        last = (x, y)
        dx, dy = tx - x, ty - y
        if log:
            log(f"cursor at ({x:.0f},{y:.0f}) -> target ({tx},{ty})")
        if abs(dx) <= tol and abs(dy) <= tol:
            return True
        if abs(dx) > 160 and not 240 <= y <= 360:
            dy, dx = 300 - y, 0                 # first get into the empty band
        elif abs(dx) > tol:
            dy = 0                              # then travel horizontally, then drop onto the target
        if abs(dx) > tol:
            gamewin.hold(["d" if dx > 0 else "a"], min(0.45, max(0.03, abs(dx) / 900.0)))
        elif abs(dy) > tol:
            gamewin.hold(["s" if dy > 0 else "w"], min(0.45, max(0.03, abs(dy) / 900.0)))
        time.sleep(0.25)
    return False

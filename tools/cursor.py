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
    im = im.convert("L")
    w, h = im.size
    px = im.load()

    def lowest(cx, cy, offs):
        m, n = 255, 0
        for dx, dy in offs:
            x, y = cx + dx, cy + dy
            if 0 <= x < w and 0 <= y < h:       # the ring may be clipped by a screen edge
                m = min(m, px[x, y])
                n += 1
        return m if n >= len(offs) * 0.55 else 0

    def score(cx, cy):
        return lowest(cx, cy, RING) - mean(cx, cy, INNER)   # interior is always darker than the ring

    def mean(cx, cy, offs):
        tot = n = 0
        for dx, dy in offs:
            x, y = cx + dx, cy + dy
            if 0 <= x < w and 0 <= y < h:
                tot += px[x, y]
                n += 1
        return tot / n if n else 0

    best = (-1e9, 0, 0)
    for cy in range(0, h, 3):                   # coarse pass
        for cx in range(0, w, 3):
            s = score(cx, cy)
            if s > best[0]:
                best = (s, cx, cy)
    _, bx, by = best
    for cy in range(by - 3, by + 4):            # fine pass
        for cx in range(bx - 3, bx + 4):
            s = score(cx, cy)
            if s > best[0]:
                best = (s, cx, cy)
    return best[1], best[2], best[0]


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
        time.sleep(0.45)
    return False

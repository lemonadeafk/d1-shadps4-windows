"""From orbit (director-mode session): Set Destination -> Tower -> LAUNCH, like a player would.

    python tools\\launch_tower.py [screenshot-prefix]

Uses open_director.py to clear popups and reach the Solar System page with the cursor on the
Tower, presses X (orbit now shows "TOWER ... // Social" and a LAUNCH button), steers the cursor
from the screen centre onto LAUNCH and presses X again.
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamewin  # noqa: E402
import open_director  # noqa: E402
import cursor  # noqa: E402


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else None
    open_director.main()
    gamewin.key("n")                 # select the Tower
    time.sleep(4)
    cursor.steer(1057, 548, log=print)   # LAUNCH (bottom right)
    time.sleep(0.5)
    if prefix:
        gamewin.shot_bg(prefix + "-launch-hover.png")
    gamewin.key("n")                 # LAUNCH
    time.sleep(6)
    if prefix:
        print(gamewin.shot_bg(prefix + "-launched.png"))


if __name__ == "__main__":
    ctypes.windll.user32.SetProcessDPIAware()
    sys.argv = sys.argv[:1] + sys.argv[1:2]
    main()

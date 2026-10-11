r"""From orbit (director-mode session): Set Destination -> Earth -> Patrol the Cosmodrome -> LAUNCH.

    python tools\launch_patrol.py [screenshot-prefix]

The Director cursor is steered open-loop from known clamps (the closed-loop finder loses the
cursor on the star chart): hold DOWN until it sits on the bottom edge, then timed nudges.
Success is checked by the caller in the guest log (activity_index=92).
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamewin  # noqa: E402
import open_director  # noqa: E402
import cursor  # noqa: E402


def main(prefix=None):
    def shot(tag):
        if prefix:
            gamewin.shot_bg(f"{prefix}-{tag}.png")

    open_director.main()
    gamewin.hold(["s"], 2.5)          # cursor to the bottom edge (the map scrolls with it)
    time.sleep(0.8)
    gamewin.hold(["w"], 0.22)         # up onto Earth
    time.sleep(1.5)
    shot("earth-hover")
    gamewin.key("n")                  # open Earth's map
    time.sleep(6)
    gamewin.hold(["w"], 0.2)          # the Patrol node sits just above-left of the cursor
    time.sleep(0.6)
    gamewin.hold(["a"], 0.05)
    time.sleep(1.5)
    shot("patrol-hover")
    gamewin.key("n")                  # select Patrol
    time.sleep(5)
    cursor.steer(1057, 548, log=None)  # LAUNCH (bottom right, orbit view)
    time.sleep(0.5)
    shot("launch-hover")
    gamewin.key("n")
    time.sleep(6)
    shot("launched")


if __name__ == "__main__":
    ctypes.windll.user32.SetProcessDPIAware()
    main(sys.argv[1] if len(sys.argv) > 1 else None)

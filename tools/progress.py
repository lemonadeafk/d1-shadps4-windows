r"""A created Guardian's own story progress: the unlock flags its completed missions set.

    python tools\progress.py [name]                 show the Guardian's flags and completions
    python tools\progress.py name --complete 163    record a mission as completed (by activity index)

The flags are served by the login server from capture-rig\guardians\<name>\flags.txt
(D1_UNLOCK_FLAGS_FILE, set by d1_launch.py for a created Guardian); the login server re-reads it
at every 503 / 205, and the game asks 205 again on each return to orbit - so a mission completed
in the world unlocks the next Director node when the player is back in orbit.

On the original service the server decided which flag a completed activity sets (the manifest's
completionFlagHash); the client's files do not hold that link. COMPLETION below is read off the
Director's own rules (tools\director_rules.py: the Earth story nodes, entries 36-40, need FLAG
132, 134, 136, 140, 237 in turn) - NIGHT-NOTES sections 89-90. Entries marked "to verify" are a
reading of the chain, not yet confirmed by unlocking the node they should open.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import new_guardian as ng  # noqa: E402

# the account flags every launch serves (d1_launch.py's D1_UNLOCK_FLAGS default)
BASE = [98, 131, 419, 440, 834, 2479, 2496, 2497, 2500, 2501, 2502, 2503, 2667, 4917, 4992, 5015, 5987, 6018]
PROLOGUE_GO = 2837          # the prologue table: activity 163 if FLAG 2837 AND NOT FLAG 836 (section 72)
PROLOGUE_DONE = 836         # presumably "prologue done" - set with A Guardian Rises' completion
# activity index -> the completion flag it sets
COMPLETION = {
    163: 132,               # A Guardian Rises -> Earth story entry 36 (to verify: should open Restoration)
    165: 134,               # Restoration -> entry 37 (to verify)
}
# 101 opens "Patrol the Cosmodrome" (user-verified, round 1); that A Guardian Rises is what grants
# it is a GUESS - the Director rules do not say which mission does
EXTRA = {163: [PROLOGUE_DONE, 101]}


def path(name):
    return os.path.join(ng.GUARDIANS, name, "flags.txt")


def read(name):
    p = path(name)
    if not os.path.exists(p):
        return BASE + [PROLOGUE_GO]          # a new Guardian: the game starts the prologue mission
    return [int(t) for t in open(p).read().replace("\n", ",").split(",") if t.strip()]


def write(name, flags):
    p = path(name)
    with open(p + ".tmp", "w") as f:
        f.write(",".join(str(x) for x in sorted(set(flags))) + "\n")
    os.replace(p + ".tmp", p)


def ensure(name):
    """The Guardian's flag file, created on first use; returns its path."""
    if not os.path.exists(path(name)):
        write(name, read(name))
    return path(name)


def complete(name, activity):
    """Record `activity` (index) as completed; returns the flags added."""
    flags = read(name)
    add = ([COMPLETION[activity]] if activity in COMPLETION else []) + EXTRA.get(activity, [])
    new = [x for x in add if x not in flags]
    if activity == 163 and PROLOGUE_GO in flags:
        flags.remove(PROLOGUE_GO)               # the prologue is done: do not start it again
    write(name, flags + new)
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("--complete", type=int)
    a = ap.parse_args()
    name = a.name or (ng.current() or (None,))[0]
    if not name:
        raise SystemExit("no Guardian named and none served")
    ensure(name)
    if a.complete is not None:
        print("added", complete(name, a.complete))
    print(name, read(name))


if __name__ == "__main__":
    main()

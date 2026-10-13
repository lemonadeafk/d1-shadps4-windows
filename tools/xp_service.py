r"""Grant XP for kills (and for finishing a mission) to the served created Guardian, live.

    python tools\xp_service.py                  follow the newest run
    python tools\xp_service.py --dry-run        only print what would be granted

How the real service did it (NIGHT-NOTES section 89): every kill makes the game send the activity
host an `incident` (udt 18, schema 0x8080097D); the server turned incidents into rewards and
pushed the changed character. Here the activity host logs each incident payload; this decodes it
with the client's own codec (object_file.exe), and for a kill raises the character_level
progression (ordinal 117, family 4/1 profile +0x3660) and the card level (family 3 +0x68, from
the game's own XP curve), then hands both objects to the login server through D1_SWAP_TRIGGER -
the same path an equip uses - which pushes them to the running game.

A kill incident's type list holds 0x2C2 and 0x8EF (11 thrall kills + the wizard in run RESPLAY);
the victim-specific ids tell the enemy apart (thrall 0x94B, wizard 0xC60). When the mission
engine sends the post-game phase, the mission's completion flag goes into the Guardian's own
flags (tools\progress.py).
XP AMOUNTS ARE PLACEHOLDERS (XP_PER below): the real values are in the investment content's
incident rewards, not decoded yet.
"""
import argparse
import glob
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import finish_character as fc  # noqa: E402
import new_guardian as ng  # noqa: E402
import progress  # noqa: E402

SWAP_TRIGGER = os.path.join(os.path.dirname(HERE), "inject", "loadout-swap.txt")
INCIDENT = "0x8080097D"
KILL = {0x2C2, 0x8EF}
# victim marker id -> (name, XP)   PLACEHOLDER amounts
XP_PER = {0xC60: ("wizard", 150), 0x94B: ("thrall", 20)}
XP_KILL_DEFAULT = ("enemy", 30)
XP_MISSION = 1500                  # PLACEHOLDER: finishing a mission (the post-game phase)
CURVE = [0, 900, 4100, 5000, 6000, 7000, 8000] + [9000] * 30 + [10000, 15000, 20000]   # character_level steps
CHARACTER_LEVEL = 117
PUSH_EVERY = 3.0                   # seconds: kills close together go out as one push
LINE = re.compile(r"CAPTURED udt 18 \(incident\) payload: ([0-9a-f]+)")
MISSION_END = "mission ends: post game"
ACTIVITY = re.compile(r"publishing activity INDEX (\d+)")


def level_of(xp):
    total, level = 0, 1
    for step in CURVE[1:]:
        total += step
        if xp < total:
            break
        level += 1
    return min(level, 40)


def incident_types(payload_hex):
    """The incident's type id list, decoded by the client's own codec."""
    tmp = tempfile.mkdtemp(prefix="d1_inc_")
    p, i = os.path.join(tmp, "p.bin"), os.path.join(tmp, "i.bin")
    open(p, "wb").write(bytes.fromhex(payload_hex))
    r = subprocess.run([fc.OBJFILE, "decode", INCIDENT, p, i], capture_output=True, text=True)
    if r.returncode:
        return []
    b = open(i, "rb").read()
    n = struct.unpack_from("<I", b, 0)[0]
    return [struct.unpack_from("<I", b, 4 + 4 * k)[0] for k in range(min(n, 50))]


def kill_xp(types):
    if not KILL <= set(types):
        return None
    for marker, (name, xp) in XP_PER.items():
        if marker in types:
            return name, xp
    return XP_KILL_DEFAULT


def apply(name, xp):
    """Write the new XP into the Guardian's profile and character; returns the level."""
    folder = os.path.join(ng.GUARDIANS, name)
    level = level_of(xp)

    def profile(b):
        n = struct.unpack_from("<I", b, 0x3660)[0]
        for k in range(n):
            if struct.unpack_from("<H", b, 0x3664 + 16 * k + 12)[0] == CHARACTER_LEVEL:
                struct.pack_into("<I", b, 0x3664 + 16 * k, xp)
                return
        struct.pack_into("<IIIH", b, 0x3664 + 16 * n, xp, 0, 0, CHARACTER_LEVEL)
        struct.pack_into("<I", b, 0x3660, n + 1)

    ng.edit(ng.PROFILE, os.path.join(folder, "profile.bin"), profile)
    ng.edit(ng.CHARACTER, os.path.join(folder, "char.bin"), lambda b: struct.pack_into("<I", b, 0x68, level))
    meta_path = os.path.join(folder, "meta.json")
    meta = json.load(open(meta_path))
    meta.update(xp=xp, level=level)
    json.dump(meta, open(meta_path, "w"))
    return level


def push(name):
    with open(SWAP_TRIGGER + ".tmp", "w") as f:
        f.write(ng.env_lines(name) + "FAMILIES=3,4\n")
    os.replace(SWAP_TRIGGER + ".tmp", SWAP_TRIGGER)


def newest_run():
    runs = sorted(glob.glob(r"C:\d1server\d1preservation\runs\*WIN-*"), key=os.path.getmtime)
    return runs[-1] if runs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cur = ng.current()
    if not cur:
        raise SystemExit("no created Guardian is served (capture-rig\\guardians\\current.txt)")
    name, _, meta = cur
    xp = meta.get("xp", 0)
    run = newest_run()
    log = os.path.join(run, "activity-host.log")
    print(time.strftime("%H:%M:%S"), "XP service: %s at %d XP (level %d), following %s" % (name, xp, level_of(xp), run), flush=True)
    # read from the start once for the activity the host publishes, then only new lines
    activity = None
    if os.path.exists(log):
        m = ACTIVITY.search(open(log, encoding="utf-8", errors="replace").read())
        activity = int(m.group(1)) if m else None
    offset, pending, since = os.path.getsize(log) if os.path.exists(log) else 0, 0, None
    while True:
        if os.path.exists(log):
            with open(log, "rb") as f:
                f.seek(offset)
                data = f.read()
            end = data.rfind(b"\n") + 1
            offset += end
            for line in data[:end].decode("utf-8", "replace").splitlines():
                m = LINE.search(line)
                if m:
                    k = kill_xp(incident_types(m.group(1)))
                    if k:
                        pending += k[1]
                        since = since or time.time()
                        print(time.strftime("%H:%M:%S"), "kill: %s +%d XP" % k, flush=True)
                elif MISSION_END in line:
                    pending += XP_MISSION
                    since = since or time.time()
                    print(time.strftime("%H:%M:%S"), "mission complete +%d XP" % XP_MISSION, flush=True)
                    # its completion flag: the Director opens the next node back in orbit
                    if activity is not None and not a.dry_run:
                        print(time.strftime("%H:%M:%S"), "activity %d completed, flags added %s"
                              % (activity, progress.complete(name, activity)), flush=True)
                elif ACTIVITY.search(line):
                    activity = int(ACTIVITY.search(line).group(1))
        if pending and time.time() - since >= PUSH_EVERY:
            before = level_of(xp)
            xp += pending
            pending, since = 0, None
            if a.dry_run:
                print(time.strftime("%H:%M:%S"), "(dry run) would push %d XP, level %d" % (xp, level_of(xp)), flush=True)
            else:
                level = apply(name, xp)
                push(name)
                print(time.strftime("%H:%M:%S"), "pushed: %d XP, level %d%s" % (
                    xp, level, "  LEVEL UP" if level > before else ""), flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    main()

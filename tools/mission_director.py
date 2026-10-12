r"""Play the mission's scripted sequences (Ghost dialogue, music cues) from the server side.

    python tools\mission_director.py [--bubble 3] [--script wall]

Waits until the newest run reaches 'activity:in_world', then sends each sequence's value
through the activity host's injection folder (tools\inject_sensor.py) - the same udt-5 sensor
frames the host sends, nothing written into the game's memory.

A kind-5 sequence record (value 0x808029A1 {i32 start, u8 counter, ...}) plays when its counter
changes (setter FUN_0040BE80). NIGHT-NOTES section 47.
"""
import argparse
import glob
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inject_sensor  # noqa: E402

WORLD = "0x80cb800d"            # act_cosmo_m0_highway
DIALOGUE = "0x3c2f5ed5"         # group of seq_d_* / seq_m_* / seq_fallen_* records

BREACH = "0xfc0e45a3"           # the Wall room's own group (bubble 3)
ACTIVITY = "0x992bb471"         # activity-wide records: objectives, cinematics, pm_in_wall
# Objectives (kind 32, value 0x80802A1B, 752 bytes; +0 = a 3-bit state). Subs and their HUD text:
#   3 ENTER THE WALL, 7 FIND A WEAPON, 11 GRAB THE RIFLE, 14 FIGHT THROUGH THE WALL,
#   17 FIGHT THROUGH THE FALLEN, 20 FIND THE SHIP, 23 FIND THE SHIP, 26 CLEAR OUT THE FALLEN.
# State 1 plays the "NEW MISSION" banner, 3 shows the objective on the HUD, 0 hides it.
HIDDEN, ANNOUNCE, ACTIVE = 0, 1, 3
OBJECTIVE_TAG = 0x80801932      # a schema the objective value needs registered in the encoder

# Steps: (seconds after the previous step, kind, ...)
#   ("seq", group, sub, name)                       play a kind-5 sequence
#   ("state", group, subs, (ch0, ch1, ch2), name)   scripted-object state channels (0..1)
#   ("gone", group, subs, name)                     remove scripted objects
#   ("objective", sub, state, name)                 a mission objective's HUD state
#   ("wait", group, kind, sub, timeout, name)       until the GAME reports that record (udt 6), or timeout
#   ("perf", group, sub, value file, name)          start an actor's performance (kind-40 sensor)
#   ("spawn", group, name[, subs])                  squad members get their actors (all, or the listed subs)
# Dialogue sequences are named by objective: seq_d_o1_* belong to ENTER THE WALL (the highway),
# seq_d_o2_* to FIND A WEAPON (inside the Wall), o3 to GRAB THE RIFLE, o4 / o5 to the later
# objectives. Subs in group DIALOGUE: o1_10 3, o1_15 4, o1_20 5, o1_20b 6, o1_20c 7, o1_20d 8,
# o2_10 9, _20 10, _30 11, _35 12, _36 13, _40 14, _50 15, _60 16, _70 17, _80 18, _90 19,
# _95 20, o3_10..50 21-25, o4_20/30/40/45 26-29, o5_10/20/30 30-32. Each is played here in its
# named order; WHICH script moment each belongs to is a guess (NIGHT-NOTES section 61).
def _line(delay, sub, name):
    return (delay, "seq", DIALOGUE, sub, "seq_d_" + name)


# Inside the Wall. The Ghost's performance flies it to the power control (o_breach_control) with
# its torch; o_breach_control channel 2 = the room's light level; the gate to the rifle =
# o_breach_gating_back + o_breach_nut_back. NIGHT-NOTES sections 54-56.
_WALL = [
    (0, "spawn", BREACH, "the Ghost appears", [95]),      # sq_nux_ghost__ghost, by the gate
    _line(1, 9, "o2_10"),
    _line(7, 10, "o2_20"),
    _line(7, 11, "o2_30"),
    (2, "perf", BREACH, 125, "ghost_perf.bin", "the Ghost flies to the power control with its torch"),
    _line(6, 12, "o2_35"),
    _line(6, 13, "o2_36"),
    # the game itself reports when the player walks to the right-hand side of the platform
    (0, "wait", BREACH, 28, 123, 20, "pm_nux_ghost_light_up_fly_to_gun"),
    (1, "state", BREACH, "0", (0.0, 0.0, 0.25), "power 25%"),
    (1, "state", BREACH, "0", (0.0, 0.0, 0.5), "power 50%"),
    (1, "state", BREACH, "0", (0.0, 0.0, 0.75), "power 75%"),
    (1, "state", BREACH, "0,1,4,8", (0.0, 0.0, 1.0), "power on"),
    (1, "seq", DIALOGUE, 0, "seq_m_cue1"),
    _line(1, 14, "o2_40"),
    _line(7, 15, "o2_50"),
    (5, "gone", BREACH, "5,6", "gate opens"),
    (1, "objective", 7, HIDDEN, "FIND A WEAPON done"),
    (1, "objective", 11, ACTIVE, "objective: GRAB THE RIFLE"),
    _line(2, 16, "o2_60"),
    (6, "seq", DIALOGUE, 33, "seq_fallen_scream_far"),
    (3, "spawn", BREACH, "the Fallen arrive"),
    _line(3, 17, "o2_70"),
    _line(8, 18, "o2_80"),
    _line(9, 19, "o2_90"),
    _line(8, 20, "o2_95"),
]
SCRIPTS = {
    # started inside the Wall (the "inside the Wall" launcher)
    "wall": [(0, "objective", 7, ACTIVE, "objective: FIND A WEAPON")] + _WALL,
    # The whole mission from its real start on the highway. Nothing happens in the Wall until
    # the game starts reporting the Wall's own records (= the player has walked in and the host
    # has switched to that bubble); 16 s later the host's follow-up frames
    # (D1_AH_SENSOR_FOLLOW_MAX=3) are over and cannot overwrite the script's values.
    "mission": [
        (0, "objective", 3, ANNOUNCE, "NEW MISSION - Restoration"),
        (7, "objective", 3, ACTIVE, "objective: ENTER THE WALL"),
        _line(2, 3, "o1_10"),
        _line(7, 4, "o1_15"),
        (0, "wait", ACTIVITY, 28, 33, 4 * 3600, "pm_in_wall (the stairs at the Wall's foot)"),
        _line(0, 6, "o1_20b"),
        (0, "wait", BREACH, 4, 0, 4 * 3600, "the player walks into the Wall"),
        (16, "objective", 3, HIDDEN, "ENTER THE WALL done"),
        (1, "objective", 7, ACTIVE, "objective: FIND A WEAPON"),
        (1, "seq", DIALOGUE, 34, "seq_fallen_scream_mid"),
    ] + _WALL,
}
SETTLE = {"wall": 50, "mission": 50}     # seconds after in_world before the first step


def sequence_value(counter, start=0):
    img = bytearray(bytes.fromhex("ffffffffff000000" + "00" * 16 + "c59d1c81ff00ffff"))
    img[0:4] = struct.pack("<i", start)
    img[4] = counter & 0xFF
    return img.hex()


def member_subs(bubble, group):
    """Squad-member (kind 2) slots of a group, from the activity host's content-derived cache."""
    path = os.path.join(os.environ["TEMP"], "d1-world-sensors", "v2-%s-%d.txt" % (WORLD[2:], bubble))
    want = "%08x" % int(group, 16)
    return [int(p[3]) for p in (l.split() for l in open(path)) if p[:1] == ["slot"] and p[1] == want and p[2] == "2"]


def newest_run():
    runs = sorted(glob.glob(r"C:\d1server\d1preservation\runs\*WIN-*"), key=os.path.getmtime)
    return runs[-1] if runs else None


def wait_in_world(timeout=900):
    t0 = time.time()
    seen = None
    while time.time() - t0 < timeout:
        run = newest_run()
        # only a run started after this script: an older finished run also says in_world
        if run and os.path.getctime(run) >= t0 - 30:
            log = os.path.join(run, "guest-stdout.log")
            try:
                with open(log, "rb") as f:
                    if b"Entering state 'activity:in_world'" in f.read():
                        return run
            except OSError:
                pass
            if run != seen:
                print("waiting for", os.path.basename(run), "to reach in_world")
                seen = run
        time.sleep(3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bubble", type=int, default=3)
    ap.add_argument("--script", default="wall", choices=sorted(SCRIPTS))
    ap.add_argument("--counter", type=int, default=1)
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()
    run = newest_run()
    if not a.no_wait:
        run = wait_in_world()
        if not run:
            raise SystemExit("the game never reached in_world")
        print("in world:", os.path.basename(run))
        time.sleep(SETTLE[a.script])  # let the host's arrival frames and their repeats finish first
    import object_state
    import sense_reports
    watcher = sense_reports.Watcher(run, a.bubble, WORLD[2:])
    os.environ["D1_ORACLE_EXTRA_TAGS"] = "%#x,%#x" % (object_state.STATE_TAG, OBJECTIVE_TAG)
    objective = open(os.path.join(os.path.dirname(HERE), "capture", "values", "objective_default.bin"), "rb").read()
    seq = 100                       # scripted-object sequence numbers only ever rise
    for step in SCRIPTS[a.script]:
        delay, kind = step[0], step[1]
        time.sleep(delay)
        if kind == "wait":
            _, _, group, wkind, sub, timeout, name = step
            hit = watcher.wait(int(group, 16), wkind, sub, timeout)
            print(time.strftime("%H:%M:%S"), name, "reported by the game" if hit else "not reported in %d s - going on" % timeout, flush=True)
            continue
        if kind == "objective":
            _, _, sub, state, name = step
            entries = ["%s:%d:%s" % (ACTIVITY, sub, (bytes([state]) + objective[1:]).hex())]
        elif kind == "seq":
            _, _, group, sub, name = step
            entries = ["%s:%d:%s" % (group, sub, sequence_value(a.counter))]
        elif kind == "perf":
            _, _, group, sub, image, name = step
            img = open(os.path.join(os.path.dirname(HERE), "capture", "values", image), "rb").read().hex()
            entries = ["%s:%d:%s" % (group, sub, img)]
        elif kind == "spawn":
            group, name = step[2], step[3]
            only = step[4] if len(step) > 4 else None
            img = open(os.path.join(os.path.dirname(HERE), "capture", "values", "member_exists.bin"), "rb").read().hex()
            entries = ["%s:%d:%s" % (group, sub, img) for sub in (only or member_subs(a.bubble, group))]
        else:
            seq += 1
            if kind == "state":
                _, _, group, subs, channels, name = step
                img = object_state.image(seq, channels).hex()
            else:
                _, _, group, subs, name = step
                img = object_state.image(seq, (0.0, 0.0, 0.0), exists=False).hex()
            entries = ["%s:%s:%s" % (group, sub, img) for sub in subs.split(",")]
        ok = inject_sensor.inject(a.bubble, entries, world=WORLD)
        print(time.strftime("%H:%M:%S"), name, "sent" if ok else "NOT picked up", flush=True)


if __name__ == "__main__":
    main()

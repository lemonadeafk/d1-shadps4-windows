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
# the file d1-responder watches (launchers set D1_SWAP_TRIGGER to it) for a loadout change
SWAP_TRIGGER = os.path.join(os.path.dirname(HERE), "inject", "loadout-swap.txt")

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
    # (pm_nux_ghost_light_up_fly_to_gun, kind 28 sub 123, is reported when the player stands at
    # the rifle - behind the gate, so it cannot come before the power-up)
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
    # The rifle (ACTIVITY kind 4 sub 6, o_weapon) has no prompt of its own: the objective's
    # player trigger (kind 29 sub 35), once the server enables it, makes the game send udt 18
    # "incident" for as long as the player stands at the rifle. The server then takes the
    # rifle away and moves the mission on. NIGHT-NOTES section 62.
    # o2_90 = "I hope you know how to use that thing" (the user identified the recording), so it
    # plays at the pickup; o2_70 / o2_80 ("they're coming for us") are the urging before it.
    (1, "trigger", 35, True, "rifle trigger armed"),
    (4, "seq", DIALOGUE, 33, "seq_fallen_scream_far"),
    _line(3, 17, "o2_70"),
    _line(8, 18, "o2_80"),
    (0, "incident", 4 * 3600, "the player reaches the rifle"),
    (0, "trigger", 35, False, "rifle trigger disarmed"),
    (0, "gone", ACTIVITY, "6", "the rifle is taken"),
    # the login server pushes the character with the Khvostov equipped (the mission launchers
    # start the player on the "unarmed" variant). tools\loadout_variant.py, section 63.
    (0, "loadout", "khvostov", "the Khvostov is handed over"),
    (1, "objective", 11, HIDDEN, "GRAB THE RIFLE done"),
    _line(0, 19, "o2_90"),
    (4, "objective", 14, ACTIVE, "objective: FIGHT THROUGH THE WALL"),
    (2, "spawn", BREACH, "the Fallen arrive"),
    _line(6, 20, "o2_95"),
]
# (group, kind, sub) cues the game reports on the way in
_PM_IN_WALL = (ACTIVITY, 28, 33)
_T_ENTER = (ACTIVITY, 29, 30)           # cosmo_m0_phase00_highway.obj_m0_phase00_m1._player_trigger
_T_IN_WALL_2 = (DIALOGUE, 29, 46)       # pt_in_wall_2
_T_FALLEN_ABOVE = (DIALOGUE, 29, 47)    # pt_fallen_above
_IN_BREACH = (BREACH, 4, 0)             # the Wall room's first scripted object: we are in its area
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
        # The way in, cued by what the game reports (positions from the trigger log, run TRIG1).
        # Each wait also ends on any LATER cue, so a player who was past a trigger before it
        # was armed cannot stall the script.
        (0, "wait_any", [_PM_IN_WALL, _T_ENTER, _T_IN_WALL_2, _T_FALLEN_ABOVE, _IN_BREACH],
         "pm_in_wall: the stairs at the Wall's foot (329, -821)"),
        _line(0, 5, "o1_20"),
        (0, "wait_any", [_T_ENTER, _T_IN_WALL_2, _T_FALLEN_ABOVE, _IN_BREACH],
         "obj_m0_phase00_m1 trigger: into the Wall's corridor (317, -820)"),
        (0, "objective", 3, HIDDEN, "ENTER THE WALL done"),
        (1, "objective", 7, ACTIVE, "objective: FIND A WEAPON"),
        (0, "wait_any", [_T_IN_WALL_2, _T_FALLEN_ABOVE, _IN_BREACH], "pt_in_wall_2: top of the inner stairs (326, -797)"),
        _line(0, 6, "o1_20b"),
        (0, "wait_any", [_T_FALLEN_ABOVE, _IN_BREACH], "pt_fallen_above (332, -797)"),
        (0, "seq", DIALOGUE, 34, "seq_fallen_scream_mid"),
        (0, "wait_any", [_IN_BREACH], "the Wall's own area (the host switches to it)"),
        # the host's frames for the new area (3 x 5 s) put every value back to its default
        (16, "objective", 7, ACTIVE, "objective: FIND A WEAPON (again, after the area switch)"),
    ] + _WALL,
}
SETTLE = {"wall": 18, "mission": 18}     # seconds after in_world before the first step


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


def wait_in_world(timeout=4 * 3600):     # creating a character first can take a while
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


def wait_incident(run, offset, timeout):
    """True once the activity host logs a udt-18 incident from the game after `offset`."""
    path = os.path.join(run, "activity-host.log")
    end = time.time() + timeout
    while time.time() < end:
        with open(path, "rb") as f:
            f.seek(offset)
            if b"CAPTURED udt 18 " in f.read():
                return True
        time.sleep(0.5)
    return False


def player_position():
    """The local player's position, read from the game (a diagnostic read, nothing written)."""
    try:
        import contextlib
        import io
        from d1guest_win import d1guest
        ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                                no_cache=False, allow_dead=True, account_soid=None, require=0)
        with contextlib.redirect_stdout(io.StringIO()):
            _, _, proc, g = d1guest.open_guest(ns)
        pool = g.base + 0x26795E0
        elems = struct.unpack("<Q", proc.read(pool + 8, 8))[0]
        return struct.unpack("<3f", proc.read(elems + 0xE0, 12))
    except Exception:
        return None


def trigger_logger(run, bubble):
    """Arm every player trigger (kind 29) of the area and write down each one the game fires.

    Triggers are disabled until the server enables them; an enabled one makes the game send an
    incident for as long as the player stands in it, so each is disarmed at its first report.
    <run>\\trigger-log.txt gets time, record name and the player's position - one playthrough
    then shows where every trigger of the mission sits and in which order they come.
    The host's frames after an area switch reset the values, so everything is re-armed 17 s
    after the game first reports the Wall's own records.
    """
    import json
    import sense_reports
    names = json.load(open(os.path.join(os.path.dirname(HERE), "capture", "values", "record_names_b3.json")))
    known = sense_reports.slots(bubble, WORLD[2:])
    # NOT pt_bubble (the Wall's sub 105): armed, it fires in the corridor (x ~355) and the game
    # dies within a second (render job, 0xBBDEDE; runs TRIG1 / TRIG2 and a live test in TRIG3).
    unsafe = {(int(BREACH, 16), 105)}
    triggers = sorted((g, sub) for (g, sub), kind in known.items() if kind == 29 and (g, sub) not in unsafe)
    watcher = sense_reports.Watcher(run, bubble, WORLD[2:])
    out = open(os.path.join(run, "trigger-log.txt"), "a", encoding="utf-8")

    def arm(which, on=True):
        value = "0100000001000000" if on else "0000000000000000"
        for i in range(0, len(which), 12):       # a few per frame keeps the frames small
            inject_sensor.inject(bubble, ["%#x:%d:%s" % (g, sub, value) for g, sub in which[i:i + 12]], world=WORLD)

    def note(text):
        out.write("%s %s\n" % (time.strftime("%H:%M:%S"), text))
        out.flush()

    arm(triggers)
    note("armed %d triggers" % len(triggers))
    fired, rearm_at, in_wall = set(), None, False
    while os.path.isdir(run):
        for when, group, kind, sub, body in watcher.poll():
            key = "%08x:%d:%d" % (group, kind, sub)
            if kind == 4 and group == int(BREACH, 16) and sub == 0 and not in_wall:
                in_wall, rearm_at = True, time.time() + 17
            if kind == 29 and (group, sub) not in fired:
                fired.add((group, sub))
                arm([(group, sub)], False)
                pos = player_position()
                note("TRIGGER %s %s at %s" % (key, names.get(key, "?"), "(%.1f, %.1f, %.1f)" % pos if pos else "?"))
            elif kind == 28 and body[:4] == "1111":
                pos = player_position()
                note("REGION  %s %s at %s" % (key, names.get(key, "?"), "(%.1f, %.1f, %.1f)" % pos if pos else "?"))
        if rearm_at and time.time() > rearm_at:
            rearm_at = None
            arm([t for t in triggers if t not in fired])
            note("re-armed after the area switch")
        time.sleep(0.5)


def main():
    armed_at = 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--bubble", type=int, default=3)
    ap.add_argument("--script", default="wall", choices=sorted(SCRIPTS))
    ap.add_argument("--counter", type=int, default=1)
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--no-trigger-log", action="store_true", help="do not arm and log the game's player triggers")
    a = ap.parse_args()
    run = newest_run()
    if not a.no_wait:
        run = wait_in_world()
        if not run:
            raise SystemExit("the game never reached in_world")
        print("in world:", os.path.basename(run))
        # let the host's arrival frames and their repeats finish first (they would overwrite
        # the script's values); MISSION_SETTLE overrides for a host with fewer repeats
        time.sleep(float(os.environ.get("MISSION_SETTLE", SETTLE[a.script])))
    import object_state
    import sense_reports
    watcher = sense_reports.Watcher(run, a.bubble, WORLD[2:], history=True)
    os.environ["D1_ORACLE_EXTRA_TAGS"] = "%#x,%#x" % (object_state.STATE_TAG, OBJECTIVE_TAG)
    objective = open(os.path.join(os.path.dirname(HERE), "capture", "values", "objective_default.bin"), "rb").read()
    seq = 100                       # scripted-object sequence numbers only ever rise
    if not a.no_trigger_log:
        import threading
        threading.Thread(target=trigger_logger, args=(run, a.bubble), daemon=True).start()
    for step in SCRIPTS[a.script]:
        delay, kind = step[0], step[1]
        time.sleep(delay)
        if kind == "wait":
            _, _, group, wkind, sub, timeout, name = step
            hit = watcher.wait(int(group, 16), wkind, sub, timeout)
            print(time.strftime("%H:%M:%S"), name, "reported by the game" if hit else "not reported in %d s - going on" % timeout, flush=True)
            continue
        if kind == "wait_any":
            _, _, cues, name = step
            want = {(int(g, 16), k, s) for g, k, s in cues}
            hit = None
            while hit is None:
                hit = next((r for r in watcher.seen if r[1:4] in want), None)
                if hit is None:
                    watcher.poll()
                    time.sleep(0.5)
            print(time.strftime("%H:%M:%S"), name, "- reported by the game (%08x %d:%d)" % hit[1:4], flush=True)
            continue
        if kind == "incident":
            _, _, timeout, name = step
            hit = watcher.wait(int(ACTIVITY, 16), 29, 35, timeout)     # obj_get_weapon's trigger
            print(time.strftime("%H:%M:%S"), name, "reported by the game" if hit else "not reported in %d s - going on" % timeout, flush=True)
            continue
        if kind == "loadout":
            # picked up by d1-responder (D1_SWAP_TRIGGER) on the game's next keepalive
            _, _, variant, name = step
            import loadout_variant
            for stale in (SWAP_TRIGGER, os.path.splitext(SWAP_TRIGGER)[0] + ".done"):
                if os.path.exists(stale):
                    os.remove(stale)
            with open(SWAP_TRIGGER, "w") as f:
                f.write(loadout_variant.swap_lines(variant))
            print(time.strftime("%H:%M:%S"), name, "requested", flush=True)
            continue
        if kind == "trigger":
            # kind-29 value (schema 0x80800463): {bool enabled, i32 limit}
            _, _, sub, on, name = step
            if on:
                armed_at = os.path.getsize(os.path.join(run, "activity-host.log"))
            entries = ["%s:%d:%s" % (ACTIVITY, sub, "0100000001000000" if on else "0000000000000000")]
        elif kind == "objective":
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
    if not a.no_trigger_log:        # keep logging triggers for as long as this run is the current one
        print(time.strftime("%H:%M:%S"), "script done; still logging triggers to trigger-log.txt", flush=True)
        while newest_run() == run and os.path.isdir(run):
            time.sleep(5)


if __name__ == "__main__":
    main()

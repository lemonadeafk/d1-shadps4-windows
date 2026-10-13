"""Unattended Tower session: launcher -> title screen -> settings screens -> orbit -> in-world.

    python tools\\autopilot.py                 # start a session and drive it into the Tower
    python tools\\autopilot.py --stop-at orbit # stop driving once in orbit
    python tools\\autopilot.py --kill          # end the running session (launcher cleans up)

Needs the persistent hosts redirect ("Allow unattended runs.cmd"), otherwise the launcher would
wait for an admin click. Screenshots of each stage land in the run folder as shot-*.png.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNS = r"C:\d1server\d1preservation\runs"
sys.path.insert(0, HERE)
import gamewin  # noqa: E402
import winproc  # noqa: E402

TOWER_ARGS = ["--inworld", "--world", "city_tower_default1", "--checksum", "0x7f0057be",
              "--bubbles", "5", "--chosen", "0-4"]


# Other destinations: world facts read from the world record (`<activity>:scenario_client` in
# capture\world-namespace.tsv, tools\world_names.py): +0x0C checksum, +0x48 bubble count, valid
# flags in the bubble table. `launch` is the tool that picks the node in the Director.
DESTINATIONS = {
    "tower": dict(args=TOWER_ARGS, env=[], launch="launch_tower.py"),
    "cosmo_patrol": dict(
        args=["--inworld", "--world", "patrol_deltas_com01", "--checksum", "0x6a556a7f",
              "--bubbles", "22", "--chosen", "0-21"],
        env=["D1_AH_SENSOR_WORLD=0x80cb87eb", "D1_AH_ACTIVITY_INDEX=92"],
        launch="launch_patrol.py"),
    # First Light (Crucible, one private bubble) as Elimination (407, the repo's measured mode).
    "pvp_moonbase": dict(
        args=["--inworld", "--world", "pvp_moonbase", "--checksum", "0x5966e491",
              "--bubbles", "1", "--chosen", "0"],
        env=["D1_AH_SENSOR_WORLD=0x80f08003", "D1_AH_ACTIVITY_INDEX=407", "D1_AH_SENSOR_PLAYER_TEAM=-1"],
        launch="launch_patrol.py"),
    # "A Guardian Rises" has no Director node for an existing character; the client loads the world
    # the activity host names, so it is reached through the patrol node with a story activity's
    # index (165 = Restoration, measured from the Director).
    "guardian_rises": dict(
        args=["--inworld", "--world", "act_cosmo_m0_highway", "--checksum", "0x8fe07299",
              "--bubbles", "22", "--chosen", "0-21"],
        # :14 = the start bubble (the one holding the content of the mission's first phase).
        # PLAYER_TEAM=-1: a story mission has no teams; the slot's team must equal the client's.
        env=["D1_AH_SENSOR_WORLD=0x80cb800d:14", "D1_AH_ACTIVITY_INDEX=163",
             "D1_AH_SENSOR_PLAYER_TEAM=-1"],
        launch="launch_patrol.py"),
    # Experiments: the same mission started in another bubble (3 = its main combat area: 30
    # squads / 45 members; 12 = 12 squads / 6 members).
    "guardian_rises_b3": dict(
        args=["--inworld", "--world", "act_cosmo_m0_highway", "--checksum", "0x8fe07299",
              "--bubbles", "22", "--chosen", "0-21"],
        env=["D1_AH_SENSOR_WORLD=0x80cb800d:3", "D1_AH_ACTIVITY_INDEX=163",
             "D1_AH_SENSOR_PLAYER_TEAM=-1"],
        launch="launch_patrol.py"),
    # ... and with the area's scripted objects (kind 4: lights, doors, grates, tripwires, chest)
    # told to exist, the way squad members are (NIGHT-NOTES section 45).
    "guardian_rises_b3_objects": dict(
        args=["--inworld", "--world", "act_cosmo_m0_highway", "--checksum", "0x8fe07299",
              "--bubbles", "22", "--chosen", "0-21"],
        env=["D1_AH_SENSOR_WORLD=0x80cb800d:3", "D1_AH_ACTIVITY_INDEX=163",
             "D1_AH_SENSOR_PLAYER_TEAM=-1",
             "D1_AH_SENSOR_KIND_VALUE=2:0x80800868:" + os.path.join(ROOT, "capture", "values", "member_exists.bin")
             + ",4:0x808007d9:" + os.path.join(ROOT, "capture", "values", "object_exists.bin"),
             "D1_AH_SENSOR_KIND_RESEQ=4", "D1_AH_SENSOR_REPEAT_MAX=8"],
        launch="launch_patrol.py"),
    # The normal start (bubble 14) with squads and scripted objects served.
    "guardian_rises_objects": dict(
        args=["--inworld", "--world", "act_cosmo_m0_highway", "--checksum", "0x8fe07299",
              "--bubbles", "22", "--chosen", "0-21"],
        env=["D1_AH_SENSOR_WORLD=0x80cb800d:14", "D1_AH_ACTIVITY_INDEX=163",
             "D1_AH_SENSOR_PLAYER_TEAM=-1",
             "D1_AH_SENSOR_KIND_VALUE=2:0x80800868:" + os.path.join(ROOT, "capture", "values", "member_exists.bin")
             + ",4:0x808007d9:" + os.path.join(ROOT, "capture", "values", "object_exists.bin"),
             "D1_AH_SENSOR_KIND_RESEQ=4"],
        launch="launch_patrol.py"),
    # The mission as it is meant to be played: start on the highway with the Ghost and the scripted
    # objects; the Wall (bubble 3) stays without squads until tools\mission_director.py --script
    # mission brings them in.
    "guardian_rises_mission": dict(
        args=["--inworld", "--world", "act_cosmo_m0_highway", "--checksum", "0x8fe07299",
              "--bubbles", "22", "--chosen", "0-21"],
        env=["D1_AH_SENSOR_WORLD=0x80cb800d:14", "D1_AH_ACTIVITY_INDEX=163",
             "D1_AH_SENSOR_PLAYER_TEAM=-1",
             "D1_AH_SENSOR_KIND_VALUE=2:0x80800868:" + os.path.join(ROOT, "capture", "values", "member_exists.bin")
             + ",4:0x808007d9:" + os.path.join(ROOT, "capture", "values", "object_exists.bin"),
             "D1_AH_SENSOR_KIND_RESEQ=4", "D1_AH_SENSOR_KIND_SKIP=2@3", "D1_AH_SENSOR_FOLLOW_MAX=3",
             "D1_AH_SENSOR_REPEAT_MAX=3",
             # the gate into the Wall's dark room is already lifted when the player gets there
             # (its state channel 2 = how far it is lifted; the state entry's schema must be
             # registered in the host's encoder)
             "D1_ORACLE_EXTRA_TAGS=0x8080279a",
             "D1_AH_SENSOR_SLOT_VALUE=" + ",".join("fc0e45a3:%d:808007d9:%s" % (sub, os.path.join(ROOT, "capture", "values", "gate_open.bin")) for sub in (5, 6))
             + ",fc0e45a3:95:80800868:" + os.path.join(ROOT, "capture", "values", "member_exists.bin")
             # the gate before the rifle (m0_power_up) served closed, so the power-up can lift
             # it partway; the roller door in front of it (o_breach_doors_lights, sub 1) served
             # open - closed it is the flat gray block the user saw ("gray box")
             + ",fc0e45a3:4:808007d9:" + os.path.join(ROOT, "capture", "values", "gate_closed.bin")
             + ",fc0e45a3:1:808007d9:" + os.path.join(ROOT, "capture", "values", "gate_open.bin")],
        launch="launch_patrol.py"),
    # The Wall with its scripted objects but NO squads: a quiet room for object-state tests.
    "guardian_rises_b3_quiet": dict(
        args=["--inworld", "--world", "act_cosmo_m0_highway", "--checksum", "0x8fe07299",
              "--bubbles", "22", "--chosen", "0-21"],
        env=["D1_AH_SENSOR_WORLD=0x80cb800d:3", "D1_AH_ACTIVITY_INDEX=163",
             "D1_AH_SENSOR_PLAYER_TEAM=-1",
             "D1_AH_SENSOR_KIND_VALUE=4:0x808007d9:" + os.path.join(ROOT, "capture", "values", "object_exists.bin"),
             "D1_AH_SENSOR_KIND_RESEQ=4", "D1_AH_SENSOR_REPEAT_MAX=8"],
        launch="launch_patrol.py"),
    "guardian_rises_b12": dict(
        args=["--inworld", "--world", "act_cosmo_m0_highway", "--checksum", "0x8fe07299",
              "--bubbles", "22", "--chosen", "0-21"],
        env=["D1_AH_SENSOR_WORLD=0x80cb800d:12", "D1_AH_ACTIVITY_INDEX=163",
             "D1_AH_SENSOR_PLAYER_TEAM=-1"],
        launch="launch_patrol.py"),
}


def log(msg):
    print(f"[auto] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def latest_run(after):
    runs = [r for r in glob.glob(os.path.join(RUNS, "*-WIN*")) if os.path.getctime(r) >= after]
    return max(runs, key=os.path.getctime) if runs else None


def states(run):
    try:
        with open(os.path.join(run, "guest-stdout.log"), encoding="utf-8", errors="replace") as f:
            return re.findall(r"Entering state '([^']+)' for reason '([^']+)'", f.read())
    except OSError:
        return []


def shot(run, label):
    try:
        p = gamewin.shot(os.path.join(run, f"shot-{time.strftime('%H%M%S')}-{label}.png"))
        log(f"screenshot {os.path.basename(p)}")
        return p
    except BaseException as e:  # noqa: BLE001 - a missing screenshot must not end the session
        log(f"screenshot failed: {e}")
        return None


def kill():
    for pid in winproc.emu_pids():
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    log("shadPS4 killed; the launcher restores settings and stops the servers")


def drive(name, stop_at, timeout, extra=(), inworld_args=(), dest="tower"):
    if winproc.emu_pids():
        raise SystemExit("an emulator is already running - refusing to start a second one")
    t0 = time.time()
    # Outside our process tree/job: stopping the autopilot must never kill the session (it did on
    # 2026-10-10 - the launcher died with it and could not restore shadPS4's settings).
    flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP | 0x01000000  # BREAKAWAY_FROM_JOB
    cmd = [sys.executable, os.path.join(ROOT, "d1_launch.py"), *DESTINATIONS[dest]["args"], "--name", name, *extra]
    try:
        subprocess.Popen(cmd, cwd=ROOT, creationflags=flags)
    except OSError:
        log("job breakaway refused - launching inside our job instead")
        subprocess.Popen(cmd, cwd=ROOT, creationflags=flags & ~0x01000000)
    run = None
    while not run and time.time() - t0 < 60:
        time.sleep(1)
        run = latest_run(t0)
    if not run:
        raise SystemExit("launcher never created a run folder")
    log(f"run {run}")
    pressed, last, shots = 0, None, set()
    end = time.time() + timeout
    while time.time() < end:
        st = states(run)
        cur = st[-1] if st else (None, None)
        if cur != last:
            log(f"state {cur[0]} ({cur[1]})")
            last = cur
        state, reason = cur
        if state == "cleanup" and reason and reason.startswith("error."):
            shot(run, "error")
            raise SystemExit(f"client gave up: {reason}")
        if not winproc.emu_pids() and time.time() - t0 > 90:   # the activity host can take ~30 s to arm
            raise SystemExit("shadPS4 is not running")
        if state == "bootflow:start" and not any(s == "bootflow:platform_signin" for s, _ in st):
            if "title" not in shots and time.time() - t0 > 20:
                shot(run, "title")
                shots.add("title")
            gamewin.tap("n")                     # the title screen's "press X"
            pressed += 1
            time.sleep(1)
            continue
        if state == "bootflow:profile_setup":
            # The first-run screens (screen bounds, brightness - which takes ◯, not ✕) are a counter
            # at static BSS 0x26B4070+0x38; 0x79E830 treats > 6 as done and requests
            # prepare_for_orbit (d1preservation status/TODO.md "UNATTENDED RUNS", 2/2 runs).
            if "settings" not in shots:
                time.sleep(1)
                shot(run, "settings")
                shots.add("settings")
                r = subprocess.run([sys.executable, os.path.join(HERE, "d1guest_win.py"), "poke",
                                    "0x26B4070", "7", "--type", "u32", "--offset", "0x38",
                                    "--experiment", "autopilot-profile-setup-skip", "--confirm"],
                                   cwd=ROOT, capture_output=True, text=True)
                log("profile_setup counter -> 7: " + ("OK" if " OK" in r.stdout else
                                                      "FAILED " + (r.stdout + r.stderr)[-300:]))
            time.sleep(2)
            continue
        if stop_at == "signin" and state == "character:signin":
            time.sleep(8)
            shot(run, "signin")
            log("at character:signin - stopping here as asked")
            return run
        if state == "setup:orbit":
            time.sleep(1)
            shot(run, "orbit")
            log(f"in orbit after {time.time() - t0:.0f} s and {pressed} key press(es)")
            if stop_at == "orbit":
                return run
            if "--skip-launch" in inworld_args:
                # Director route: pick the Tower and press LAUNCH like a player; the game leaves
                # orbit by itself and d1_inworld.py only does the post-launch steps.
                log("director route: Set Destination -> Tower -> LAUNCH")
                subprocess.run([sys.executable, os.path.join(HERE, DESTINATIONS[dest]["launch"]),
                                os.path.join(run, "director")], cwd=ROOT, check=True)
                while time.time() < end and "activity:initial_slice_set_loading" not in last_state(run):
                    time.sleep(0.5)
                # Nothing is poked on this route: the activity host serves the lifetime phase and
                # seats our player in a slot (d1_launch.py --director), and the game spawns the
                # Guardian through its own gates (NIGHT-NOTES section 14).
                while time.time() < end and "activity:in_world" not in last_state(run):
                    time.sleep(0.5)
                time.sleep(2)
                shot(run, "inworld")
                log(f"state {last_state(run)}; in the Tower via the Director with no pokes")
                return run
            proc = subprocess.Popen([sys.executable, os.path.join(HERE, "d1_inworld.py"), *inworld_args], cwd=ROOT,
                                    stdout=open(os.path.join(run, "inworld.log"), "w"),
                                    stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONUNBUFFERED="1"))
            while time.time() < end:
                time.sleep(2)
                text = open(os.path.join(run, "inworld.log"), encoding="utf-8", errors="replace").read()
                if "holding the curtain suppress" in text:
                    time.sleep(5)
                    shot(run, "inworld")
                    log("in world; in_world script is holding the curtain suppress")
                    return run
                if proc.poll() is not None:
                    shot(run, "inworld-failed")
                    raise SystemExit("d1_inworld.py ended early - see " + os.path.join(run, "inworld.log"))
            break
        time.sleep(0.3)
    shot(run, "timeout")
    raise SystemExit(f"timed out in state {last}")


def last_state(run):
    """The newest world-controller state named in the guest log."""
    try:
        text = open(os.path.join(run, "guest-stdout.log"), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""
    i = text.rfind("Entering state '")
    return text[i:i + 80] if i >= 0 else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stop-at", choices=["signin", "orbit", "inworld"], default="inworld")
    ap.add_argument("--env", action="append", default=[], help="passed to d1_launch.py --env")
    ap.add_argument("--name", default="AUTO")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--kill", action="store_true")
    ap.add_argument("--gpu", action="append", default=[], help="passed to d1_launch.py --gpu")
    ap.add_argument("--renderdoc", action="store_true", help="passed to d1_launch.py")
    ap.add_argument("--no-spawn", action="store_true", help="passed to d1_inworld.py")
    ap.add_argument("--director", action="store_true",
                    help="reach the Tower the real way: Director -> Tower -> LAUNCH (no launch poke)")
    ap.add_argument("--destination", choices=sorted(DESTINATIONS), default="tower")
    a = ap.parse_args()
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
    if a.kill:
        kill()
        return 0
    extra = [x for g in a.gpu for x in ("--gpu", g)] + (["--renderdoc"] if a.renderdoc else [])
    extra += [x for e in DESTINATIONS[a.destination]["env"] + a.env for x in ("--env", e)]
    inworld_args = ["--no-spawn"] if a.no_spawn else []
    if a.director:
        extra += ["--director"]
        inworld_args += ["--skip-launch"]
    run = drive(a.name, a.stop_at, a.timeout, extra, inworld_args, a.destination)
    print(f"RUN {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

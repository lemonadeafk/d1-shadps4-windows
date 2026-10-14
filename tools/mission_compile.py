r"""Compile a mission's event script for the activity host's mission engine.

    python tools\mission_compile.py [--script mission|wall|restoration] [--out inject\mission]

The event scripts (cue -> steps: tools\mission_director.py EVENT_SCRIPTS for A Guardian Rises,
tools\mission_restoration.py for Restoration; MISSIONS below says which world and area each runs
in) are turned into <out>\mission.txt plus one finished udt-5 frame per step (built now with
sensor_frame.exe, so nothing is encoded while the player waits). d1-activity-host loads it with
D1_AH_MISSION=<out>\mission.txt and plays it: each cue's steps start the moment the client first
reports that record, a zero-delay step leaving with the very frame that carried the report
(d1-activity-host src\mission.rs).

Also written: the trigger answers (inject\trigger-ready, D1_AH_INCIDENT_READY_DIR) - every player
trigger is armed at the start and switched off again by the host as soon as it fires.
NIGHT-NOTES section 84.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inject_sensor  # noqa: E402
import mission_director as md  # noqa: E402
import object_state  # noqa: E402
import sense_reports  # noqa: E402

ROOT = os.path.dirname(HERE)
VALUES = os.path.join(ROOT, "capture", "values")
SETTLE = 18.0           # seconds after the client's first report before the "start" cue's steps
# A squad member's last report when it dies starts with these bits (the four thralls killed in run
# RES4, and no other report; NIGHT-NOTES section 87). Cue ("dead") = that member's death.
DEATH_BITS = "1000000010100000110"


def _missions():
    import mission_restoration as res
    rises = dict(world=md.WORLD, bubble=3, objectives=md.ACTIVITY,
                 skip={(int(md.BREACH, 16), 105)},                  # pt_bubble: section 70
                 # after the area switch the host's arrival frames reset the triggers: arm them
                 # again (the ones that already fired are switched off again at once by their
                 # prepared answer)
                 rearm="%s:4:0" % md.BREACH[2:],
                 # the graveyard (12) and the hangar (13): their records' frames are built for
                 # their own area, and their triggers are armed when the player gets there (the
                 # first report of one of the area's objects) - NIGHT-NOTES section 97
                 group_bubbles={int(md.BREACH, 16): 3, int(md.GRAVEYARD, 16): 12, int(md.HANGAR, 16): 13},
                 areas={12: "%s:4:0" % md.GRAVEYARD[2:], 13: "%s:4:2" % md.HANGAR[2:]})
    return {
        "mission": dict(rises, script=md.EVENT_SCRIPTS["mission"]),
        "wall": dict(rises, script=md.EVENT_SCRIPTS["wall"]),
        "restoration": dict(world=res.WORLD, bubble=res.BUBBLE, objectives=res.MISSION, skip=set(),
                            rearm=None, script=res.EVENT_SCRIPT),
    }


class Compiler:
    def __init__(self, out, world=md.WORLD, bubble=3, objectives=md.ACTIVITY, group_bubbles=None):
        self.out, self.world, self.bubble, self.objectives = out, world, bubble, objectives
        self.group_bubbles = group_bubbles or {}
        self.n, self.seq = 0, 100
        self.objective = open(os.path.join(VALUES, "objective_default.bin"), "rb").read()
        self.jobs = []
        os.environ["D1_ORACLE_EXTRA_TAGS"] = "%#x,%#x" % (object_state.STATE_TAG, md.OBJECTIVE_TAG)

    def frame(self, entries, phase=None, bubble=None):
        """Queue a frame for `entries` (every frame also carries the lifetime phase: 3 = play
        unless given), built for the area of its records' group; returns its file name."""
        if bubble is None:
            groups = {int(e.split(":")[0], 16) for e in entries}
            known = [self.group_bubbles[g] for g in groups if g in self.group_bubbles]
            bubble = known[0] if known else self.bubble
        self.n += 1
        name = "%03d.udt5" % self.n
        path = os.path.join(self.out, name)
        args = list(entries)
        if sum(len(e) for e in entries) > 20000:
            listing = path + ".entries"
            with open(listing, "w") as f:
                f.write("\n".join(entries))
            args = ["@" + listing]
        env = dict(os.environ, SENSOR_FRAME_PHASE=str(phase)) if phase is not None else None
        self.jobs.append(subprocess.Popen([inject_sensor.SENSOR_FRAME, self.world, str(bubble), path, *args],
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env))
        if len(self.jobs) >= 8:
            self.flush()
        return name

    def flush(self):
        for p in self.jobs:
            out = p.communicate()[0]
            if p.returncode:
                raise SystemExit("sensor_frame failed: %s" % out.decode(errors="replace")[-400:])
        self.jobs = []

    def entries(self, step):
        """The sensor entries of one step (the same values mission_director.play sends)."""
        kind = step[1]
        if kind == "objective":
            _, _, sub, state, name = step
            return name, ["%s:%d:%s" % (self.objectives, sub, (bytes([state]) + self.objective[1:]).hex())]
        if kind == "seq":
            _, _, group, sub, name = step
            return name, ["%s:%d:%s" % (group, sub, md.sequence_value(1))]
        if kind == "perf":
            _, _, group, sub, image, name = step
            return name, ["%s:%d:%s" % (group, sub, open(os.path.join(VALUES, image), "rb").read().hex())]
        if kind == "squad":                         # (delay, "squad", group, [subs], name)
            # a squad without member records spawns when each slot of its composition gets an
            # alive count (value +0x2C = slots, +0x30 i16[] = 1 each; NIGHT-NOTES 93-94)
            _, _, group, subs, name = step
            sizes = json.load(open(os.path.join(VALUES, "squad_sizes_%s.json" % self.world[2:].lower())))
            entries = []
            for sub in subs:
                img = bytearray(open(os.path.join(VALUES, "default_kind1.bin"), "rb").read())
                n = sizes["%08x:%d" % (int(group, 16), sub)]
                struct.pack_into("<I", img, 0x2C, n)
                for k in range(n):
                    struct.pack_into("<h", img, 0x30 + 2 * k, 1)
                entries.append("%s:%d:%s" % (group, sub, img.hex()))
            return name, entries
        if kind == "members":                       # (delay, "members", group, [subs], name)
            _, _, group, subs, name = step
            img = open(os.path.join(VALUES, "member_exists.bin"), "rb").read().hex()
            return name, ["%s:%d:%s" % (group, sub, img) for sub in subs]
        if kind == "spawn":
            group, name = step[2], step[3]
            only = step[4] if len(step) > 4 else None
            img = open(os.path.join(VALUES, "member_exists.bin"), "rb").read().hex()
            if isinstance(only, str):
                only = md._squads(*only.split(","))
                if not only:
                    return name, []
            return name, ["%s:%d:%s" % (group, sub, img) for sub in (only or md.member_subs(self.bubble, group))]
        if kind in ("state", "gone"):
            self.seq += 1
            if kind == "state":
                _, _, group, subs, channels, name = step
                img = object_state.image(self.seq, channels, snap=False).hex()
            else:
                _, _, group, subs, name = step
                img = object_state.image(self.seq, (0.0, 0.0, 0.0), exists=False).hex()
            return name, ["%s:%s:%s" % (group, sub, img) for sub in str(subs).split(",")]
        raise SystemExit("step kind %r cannot be compiled" % kind)

    @staticmethod
    def cue(c):
        """(group, kind, sub[, "changed" | "dead" | "bits=..."]) as mission.txt writes it."""
        if c[0] == "kills":                         # ("kills", n, cue): n kills after cue
            return "kills:%d>%s" % (c[1], Compiler.cue(c[2]))
        s = "%s:%d:%d" % (c[0][2:], c[1], c[2])
        if len(c) > 3:
            s += ":" + {"dead": "bits=" + DEATH_BITS}.get(c[3], c[3])
        return s

    def area_triggers(self, bubble, skip=()):
        return sorted((g, sub) for (g, sub), k in sense_reports.slots(bubble, self.world[2:]).items()
                      if k == 29 and (g, sub) not in skip)

    def arm_frames(self, bubble, triggers):
        return [self.frame(["%#x:%d:0100000001000000" % t for t in triggers[i:i + 12]], bubble=bubble)
                for i in range(0, len(triggers), 12)]

    def compile(self, script, skip=(), rearm=None, areas=None):
        lines = []
        triggers = self.area_triggers(self.bubble, skip)
        arm = self.arm_frames(self.bubble, triggers)
        answers = {self.bubble: triggers}
        for cue, steps in script:
            if cue == "start":
                lines.append("cue\tstart")
                # armed once the host's arrival frames are over (they reset the triggers)
                lines += ["%.2f\tframe\t%s\tarm the player triggers" % (SETTLE, f) for f in arm]
                at = SETTLE
            else:
                lines.append("cue\t%s" % self.cue(cue))
                at = 0.0
            for step in steps:
                at += step[0]
                kind = step[1]
                if kind == "fire":
                    c = step[2]
                    lines.append("%.2f\tfire\t%s\t%s" % (at, self.cue(c), step[3]))
                elif kind == "phase":                   # (delay, "phase", n, name): the lifetime phase
                    # 6 = "MISSION END: seconds remaining", 7 = post game (rewards screens),
                    # 9 = "ROUND COMPLETED" scoreboard. Later frames carry phase 3 again, so an
                    # ending phase must be the script's last frame. NIGHT-NOTES section 88.
                    lines.append("%.2f\tframe\t%s\t%s" % (at, self.frame([], phase=step[2]), step[3]))
                elif kind == "countdown":               # (delay, "countdown", seconds, name)
                    # lifetime phase 6 "MISSION END: Seconds remaining: N", one frame per second:
                    # the HUD redraws the number only when the lifetime_timer record changes
                    # (4786c0e0 kind 17 sub 2; base in 1/15 s, running 0; NIGHT-NOTES 87-88)
                    for left in range(step[2], -1, -1):
                        img = bytearray(36)
                        struct.pack_into("<iiiii", img, 4, 0, step[2] * 15, left * 15, step[2] * 15, 0)
                        f = self.frame(["0x4786c0e0:2:%s" % img.hex()], phase=6)
                        lines.append("%.2f\tframe\t%s\t%s (%d s)" % (at + step[2] - left, f, step[3], left))
                    at += step[2]
                elif kind == "loadout":
                    import loadout_variant
                    name = "loadout-%s.txt" % step[2]
                    with open(os.path.join(self.out, name), "w") as f:
                        f.write(loadout_variant.swap_lines(step[2]))
                    lines.append("%.2f\tfile\t%s\t%s\t%s" % (at, name, md.SWAP_TRIGGER, step[3]))
                else:
                    label, entries = self.entries(step)
                    if entries:
                        lines.append("%.2f\tframe\t%s\t%s" % (at, self.frame(entries), label))
        if rearm:
            lines.append("cue\t%s" % rearm)
            lines += ["17\tframe\t%s\tre-arm the player triggers" % f for f in arm]
        for bubble, cue in (areas or {}).items():
            # another area of the mission: arm its triggers once its arrival frames are over
            area = self.area_triggers(bubble, skip)
            answers[bubble] = area
            lines.append("cue\t%s" % cue)
            lines += ["17\tframe\t%s\tarm area %d's player triggers" % (f, bubble)
                      for f in self.arm_frames(bubble, area)]
        self.flush()
        with open(os.path.join(self.out, "mission.txt"), "w", encoding="utf-8") as f:
            f.write("# compiled by tools\\mission_compile.py\n")
            f.write("\n".join(lines) + "\n")
        # the answer to each trigger: switch it off (sent by the host the moment it fires)
        ready = os.path.join(inject_sensor.INJECT, "trigger-ready")
        shutil.rmtree(ready, ignore_errors=True)
        os.makedirs(ready)
        jobs = []
        done = set()
        for bubble, area in answers.items():
            for g, sub in area:
                if (g, sub) in done:            # mission-wide triggers are in every area
                    continue
                done.add((g, sub))
                jobs.append(subprocess.Popen([inject_sensor.SENSOR_FRAME, self.world, str(bubble),
                                              os.path.join(ready, "%08x-%d.udt5" % (g, sub)),
                                              "%#x:%d:0000000000000000" % (g, sub)],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                if len(jobs) >= 8:
                    [p.wait() for p in jobs]
                    jobs = []
        [p.wait() for p in jobs]
        return len(lines), self.n


def main():
    missions = _missions()
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="mission", choices=sorted(missions))
    ap.add_argument("--out", default=os.path.join(ROOT, "inject", "mission"))
    a = ap.parse_args()
    shutil.rmtree(a.out, ignore_errors=True)
    os.makedirs(a.out)
    m = missions[a.script]
    n_lines, n_frames = Compiler(a.out, m["world"], m["bubble"], m["objectives"], m.get("group_bubbles")).compile(
        m["script"], m["skip"], m["rearm"], m.get("areas"))
    print("%s: %d lines, %d frames" % (os.path.join(a.out, "mission.txt"), n_lines, n_frames))


if __name__ == "__main__":
    main()

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
import os
import shutil
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
                 rearm="%s:4:0" % md.BREACH[2:])
    return {
        "mission": dict(rises, script=md.EVENT_SCRIPTS["mission"]),
        "wall": dict(rises, script=md.EVENT_SCRIPTS["wall"]),
        "restoration": dict(world=res.WORLD, bubble=res.BUBBLE, objectives=res.MISSION, skip=set(),
                            rearm=None, script=res.EVENT_SCRIPT),
    }


class Compiler:
    def __init__(self, out, world=md.WORLD, bubble=3, objectives=md.ACTIVITY):
        self.out, self.world, self.bubble, self.objectives = out, world, bubble, objectives
        self.n, self.seq = 0, 100
        self.objective = open(os.path.join(VALUES, "objective_default.bin"), "rb").read()
        self.jobs = []
        os.environ["D1_ORACLE_EXTRA_TAGS"] = "%#x,%#x" % (object_state.STATE_TAG, md.OBJECTIVE_TAG)

    def frame(self, entries):
        """Queue a frame for `entries`; returns its file name."""
        self.n += 1
        name = "%03d.udt5" % self.n
        path = os.path.join(self.out, name)
        args = list(entries)
        if sum(len(e) for e in entries) > 20000:
            listing = path + ".entries"
            with open(listing, "w") as f:
                f.write("\n".join(entries))
            args = ["@" + listing]
        self.jobs.append(subprocess.Popen([inject_sensor.SENSOR_FRAME, self.world, str(self.bubble), path, *args],
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
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
        s = "%s:%d:%d" % (c[0][2:], c[1], c[2])
        if len(c) > 3:
            s += ":" + {"dead": "bits=" + DEATH_BITS}.get(c[3], c[3])
        return s

    def compile(self, script, skip=(), rearm=None):
        lines = []
        triggers = sorted((g, sub) for (g, sub), k in sense_reports.slots(self.bubble, self.world[2:]).items()
                          if k == 29 and (g, sub) not in skip)
        arm = [self.frame(["%#x:%d:0100000001000000" % t for t in triggers[i:i + 12]])
               for i in range(0, len(triggers), 12)]
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
        self.flush()
        with open(os.path.join(self.out, "mission.txt"), "w", encoding="utf-8") as f:
            f.write("# compiled by tools\\mission_compile.py\n")
            f.write("\n".join(lines) + "\n")
        # the answer to each trigger: switch it off (sent by the host the moment it fires)
        ready = os.path.join(inject_sensor.INJECT, "trigger-ready")
        shutil.rmtree(ready, ignore_errors=True)
        os.makedirs(ready)
        jobs = []
        for g, sub in triggers:
            jobs.append(subprocess.Popen([inject_sensor.SENSOR_FRAME, self.world, str(self.bubble),
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
    n_lines, n_frames = Compiler(a.out, m["world"], m["bubble"], m["objectives"]).compile(
        m["script"], m["skip"], m["rearm"])
    print("%s: %d lines, %d frames" % (os.path.join(a.out, "mission.txt"), n_lines, n_frames))


if __name__ == "__main__":
    main()

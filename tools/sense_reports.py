r"""Decode what the GAME reports to the activity host (udt 6 sensor_sense_update).

    python tools\sense_reports.py <run dir> <bubble> [kind ...]

The client sends its own view of the mission records: squads / members (kinds 1, 2), objectives
(3), scripted objects (4), player slots (12) and - the useful ones - the player-driven records
it evaluates itself (kind 28 pm_*: sent when the player enters and again when they leave).
Each report is {name ref, body}; the name ref is 55 bits, MSB first: u32 group hash,
7 bits kind + 1, 16 bits sub + 0x8000. The activity host logs every payload; this reads the log.
NIGHT-NOTES section 57.
"""
import os
import re
import sys
import time

WORLD = "80cb800d"
LINE = re.compile(r"(\d\d:\d\d:\d\d)\.\d+Z.*CAPTURED udt 6 .*payload: ([0-9a-f]+)")


def slots(bubble, world=WORLD):
    """{(group, sub): kind} from the activity host's content-derived cache."""
    s = {}
    path = os.path.join(os.environ["TEMP"], "d1-world-sensors", "v2-%s-%d.txt" % (world, bubble))
    for line in open(path):
        p = line.split()
        if p[:1] == ["slot"]:
            s[(int(p[1], 16), int(p[3]))] = int(p[2])
    return s


def reports(payload_hex, known):
    """[(group, kind, sub, body bits)] of one payload; refs are found by matching known slots."""
    b = bin(int(payload_hex, 16))[2:].zfill(len(payload_hex) * 4)
    groups = {g for g, _ in known}
    found, i = [], 0
    while i + 55 <= len(b):
        h = int(b[i:i + 32], 2)
        if h in groups:
            kind = int(b[i + 32:i + 39], 2) - 1
            sub = int(b[i + 39:i + 55], 2) - 0x8000
            if known.get((h, sub)) == kind:
                found.append((i, h, kind, sub))
                i += 55
                continue
        i += 1
    return [(h, kind, sub, b[i + 55:(found[n + 1][0] if n + 1 < len(found) else len(b))])
            for n, (i, h, kind, sub) in enumerate(found)]


class Watcher:
    """Follows a run's activity-host.log; wait() returns when the game reports a record."""

    def __init__(self, run, bubble, world=WORLD):
        self.path = os.path.join(run, "activity-host.log")
        self.known = slots(bubble, world)
        self.offset = os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def poll(self):
        out = []
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        end = data.rfind(b"\n") + 1
        self.offset += end
        for line in data[:end].decode("utf-8", "replace").splitlines():
            m = LINE.search(line)
            if m:
                out += [(m.group(1),) + r for r in reports(m.group(2), self.known)]
        return out

    def wait(self, group, kind, sub, timeout):
        end = time.time() + timeout
        while time.time() < end:
            for r in self.poll():
                if r[1:4] == (group, kind, sub):
                    return r
            time.sleep(0.5)
        return None


if __name__ == "__main__":
    known = slots(int(sys.argv[2]))
    kinds = {int(k) for k in sys.argv[3:]}
    for line in open(os.path.join(sys.argv[1], "activity-host.log"), encoding="utf-8", errors="replace"):
        m = LINE.search(line)
        if m:
            for h, kind, sub, body in reports(m.group(2), known):
                if not kinds or kind in kinds:
                    print(m.group(1), "kind %2d %08x:%d %s" % (kind, h, sub, body[:96]))

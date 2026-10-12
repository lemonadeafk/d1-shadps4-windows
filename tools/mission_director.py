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

# Steps: (seconds after the previous step, kind, ...)
#   ("seq", group, sub, name)                       play a kind-5 sequence
#   ("state", group, subs, (ch0, ch1, ch2), name)   scripted-object state channels (0..1)
#   ("gone", group, subs, name)                     remove scripted objects
#   ("spawn", group, name[, subs])                  squad members get their actors (all, or the listed subs)
SCRIPTS = {
    # Inside the Wall: the Ghost's first lines over the music cue, then the power comes up
    # (o_breach_control channel 2 = the room's light level) and the gate to the rifle opens
    # (o_breach_gating_back + o_breach_nut_back removed). NIGHT-NOTES section 54.
    "wall": [
        (0, "spawn", BREACH, "the Ghost appears", [95]),      # sq_nux_ghost__ghost, by the gate
        (4, "seq", DIALOGUE, 0, "seq_m_cue1"),
        (1, "seq", DIALOGUE, 3, "seq_d_o1_10"),
        (8, "seq", DIALOGUE, 4, "seq_d_o1_15"),
        (6, "state", BREACH, "0", (0.0, 0.0, 0.25), "power 25%"),
        (1, "state", BREACH, "0", (0.0, 0.0, 0.5), "power 50%"),
        (1, "state", BREACH, "0", (0.0, 0.0, 0.75), "power 75%"),
        (1, "state", BREACH, "0,1,4,8", (0.0, 0.0, 1.0), "power on"),
        (3, "seq", DIALOGUE, 5, "seq_d_o1_20"),
        (3, "gone", BREACH, "5,6", "gate opens"),
        (5, "seq", DIALOGUE, 33, "seq_fallen_scream_far"),
        (4, "spawn", BREACH, "the Fallen arrive"),
        (2, "seq", DIALOGUE, 6, "seq_d_o1_20b"),
        (8, "seq", DIALOGUE, 7, "seq_d_o1_20c"),
    ],
}


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
    if not a.no_wait:
        run = wait_in_world()
        if not run:
            raise SystemExit("the game never reached in_world")
        print("in world:", os.path.basename(run))
        time.sleep(50)              # let the host's arrival frames and their repeats finish first
    import object_state
    os.environ["D1_ORACLE_EXTRA_TAGS"] = hex(object_state.STATE_TAG)
    seq = 100                       # scripted-object sequence numbers only ever rise
    for step in SCRIPTS[a.script]:
        delay, kind = step[0], step[1]
        time.sleep(delay)
        if kind == "seq":
            _, _, group, sub, name = step
            entries = ["%s:%d:%s" % (group, sub, sequence_value(a.counter))]
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

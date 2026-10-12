r"""Turn the game's "create character" request into the Guardian the server then serves.

    python tools\creation_service.py <run dir>

The login server writes a transcript of investment 501 (create-character-<t>.txt: race,
gender, class and the customization block the player chose) into the run directory and waits
for <run dir>\create-ready.txt before it answers (D1_CREATE_READY). This builds the Guardian
with tools\new_guardian.py and writes that file. NIGHT-NOTES section 66.
"""
import glob
import os
import re
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import new_guardian  # noqa: E402

SWAP_TRIGGER = os.path.join(os.path.dirname(HERE), "inject", "loadout-swap.txt")
FIELD = re.compile(r"^f\d+\s+@\+0x([0-9a-f]+)\s+(i16\[3\]|i16|i8|u32 raw)(?: \(\d+b\))?\s+(.+?)(?:\s+<-.*)?$")


def parse(path):
    """(race, gender, class, 36-byte customization block) from a transcript."""
    ident, block = {}, bytearray(36)
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^(race|gender|class)\s+(\d+)", line)
        if m:
            ident[m.group(1)] = int(m.group(2))
            continue
        m = FIELD.match(line.rstrip())
        if not m:
            continue
        off, kind, value = int(m.group(1), 16) - 4, m.group(2), m.group(3).strip()
        if kind == "i16":
            struct.pack_into("<h", block, off, int(value))
        elif kind == "i8":
            struct.pack_into("<b", block, off, int(value))
        elif kind == "i16[3]":
            struct.pack_into("<3h", block, off, *[int(v) for v in value.strip("[]").split(",")])
        else:
            struct.pack_into("<I", block, off, int(value, 16))
    return ident.get("race", 0), ident.get("gender", 0), ident.get("class", 0), bytes(block)


def main():
    run = sys.argv[1]
    seen = set(glob.glob(os.path.join(run, "create-character-*.txt")))
    print("watching", run, flush=True)
    while os.path.isdir(run):
        for path in sorted(set(glob.glob(os.path.join(run, "create-character-*.txt"))) - seen):
            seen.add(path)
            time.sleep(0.3)                       # let the server finish writing it
            race, gender, cls, block = parse(path)
            print(time.strftime("%H:%M:%S"), "create: class %d race %d gender %d custom %s" % (cls, race, gender, block.hex()), flush=True)
            try:
                new_guardian.build("created", cls, race, gender, block)
            except SystemExit as e:
                print("build failed:", e, flush=True)
                continue
            with open(os.path.join(new_guardian.GUARDIANS, "current.txt"), "w") as f:
                f.write("created")           # later launches serve this Guardian (d1_launch.py)
            # The server has already answered (holding the answer for the ~20 s the build
            # takes crashed the game, run CREATE3), so the new Guardian replaces the default
            # one the same way an equip does: content variables + a live push of every family
            # the game has subscribed to, item elements included.
            for stale in (SWAP_TRIGGER, os.path.splitext(SWAP_TRIGGER)[0] + ".done"):
                if os.path.exists(stale):
                    os.remove(stale)
            tmp = SWAP_TRIGGER + ".tmp"
            with open(tmp, "w") as f:
                f.write(new_guardian.env_lines("created") + "FAMILIES=0,3,4\nFAMILY4=all\n")
            os.replace(tmp, SWAP_TRIGGER)
            print(time.strftime("%H:%M:%S"), "pushed", flush=True)
        time.sleep(0.3)


if __name__ == "__main__":
    main()

r"""Every squad's designed size (its composition's member count), for the mission compiler.

    python tools\squad_sizes.py <world tag> <dump dir>     ->  capture\values\squad_sizes_<world>.json

<dump dir> holds world_sensors' per-bubble record dumps (D1_WS_DUMP=<dir>\<bubble>, one run per
bubble): files "<group>-k1-s<sub>-...bin" are squad records. A squad record names its squad
definition (u32 at +0x70); the definition names its composition (the one 0x80Cxxxxx tag other
than itself); the composition's member count is the u16 at +0x20 (checked against four squads
with authored members: scare01 1, basement thrall01 7, troopers01 3, wizard01 1 - NIGHT-NOTES
section 94). A squad without member records spawns when the server gives each of those slots an
alive count (squad value +0x2C = slots, +0x30 i16[] = 1 each; section 93).
"""
import glob
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import talent_grid as tg  # noqa: E402


def composition(squad_def):
    b = tg._entry(squad_def)
    tags = {struct.unpack_from("<I", b, o)[0] for o in range(0, len(b) - 3, 4)}
    tags = sorted(t for t in tags if (t >> 20) == 0x80C and t != squad_def)
    return tags[0] if len(tags) == 1 else None


def main():
    world, dump = sys.argv[1], sys.argv[2]
    out = {}
    for f in glob.glob(os.path.join(dump, "*", "*-k1-s*-*.bin")):
        m = re.match(r"([0-9a-f]{8})-k1-s(\d+)-", os.path.basename(f))
        key = "%s:%s" % m.groups()
        if key in out:
            continue
        squad_def = struct.unpack_from("<I", open(f, "rb").read(), 0x70)[0]
        comp = composition(squad_def)
        if comp:
            out[key] = struct.unpack_from("<H", tg._entry(comp), 0x20)[0]
    path = os.path.join(os.path.dirname(HERE), "capture", "values", "squad_sizes_%s.json" % world[2:].lower())
    json.dump(dict(sorted(out.items())), open(path, "w"), indent=0)
    print(path, len(out), "squads")


if __name__ == "__main__":
    main()

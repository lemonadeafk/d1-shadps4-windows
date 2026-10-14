r"""Build a geared Hunter with a chosen loadout as a served Guardian folder.

    python tools\custom_loadout.py [name]          (default name: hunter-custom)
    then serve it:  capture-rig\guardians\current.txt = <name>

Items are content indices (capture-rig\item-names.tsv, from tools\game_strings.py items). The
served Hunter's element files are the template (tools\new_guardian.py stage): each file keeps its
bucket and SOID position and gets the chosen item; files not listed keep the Hunter's item
(subclass, Ghost, ship, emotes, ...). Equipped = the first file of a bucket; later files of the
same bucket are backpack spares. Then the same rebuild / art table / assemble as
new_guardian.build's geared path. The Guardian's flags (tools\progress.py) are the account
defaults plus the story completions, so it does not start the prologue.
"""
import glob
import json
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import new_guardian as ng  # noqa: E402
import progress  # noqa: E402
import talent_grid  # noqa: E402

# the user's loadout (2026-10-13)
LOADOUT = {
    "01-Primary Weapons": 6332,     # Burning Eye (scout rifle)
    "13-Primary Weapons": 3321,     # Jewel of Osiris (hand cannon, backpack)
    "02-Special Weapons": 2229,     # Found Verdict (shotgun)
    "19-Special Weapons": 2856,     # Black Hammer (sniper, backpack)
    "03-Heavy Weapons": 5141,       # Raze-Lighter (sword)
    "20-Heavy Weapons": 2858,       # Hunger of Crota (rocket launcher, backpack)
    "05-Helmet": 5728,              # Spliced Nanomania Mask
    "06-Gauntlets": 5725,           # Spliced Nanomania Grasps
    "07-Chest Armor": 5726,         # Spliced Nanomania Vest
    "08-Leg Armor": 5729,           # Spliced Nanomania Boots
    "09-Class Armor": 5727,         # Spliced Nanomania Cloak
}
LEVEL, LIGHT = 40, 385


def build(name):
    out = os.path.join(ng.GUARDIANS, name)
    inv = os.path.join(out, "inventory")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    files = sorted(glob.glob(os.path.join(ng.TEMPLATE, "*.bin")))
    stems = [os.path.basename(p)[:-4] for p in files]
    for stem in LOADOUT:
        if stem not in stems:
            raise SystemExit("the template has no %s.bin" % stem)
    ng.stage(inv, [(s[3:], LOADOUT.get(s)) for s in stems])
    ng.run("inventory", "rebuild", "--dir", inv, "--level", str(LEVEL))
    grid = []
    ng.edit(ng.ELEMENT, os.path.join(inv, "00-Subclass.bin"), lambda b: grid.append(struct.unpack_from("<H", b, 0x58)[0]))
    active = talent_grid.default_active(grid[0])
    nodes = ["--level", str(LEVEL), "--subclass-nodes", ",".join(str(n) for n in active)]
    ng.run("inventory", "rebuild", "--dir", inv, *nodes)
    # the art table is one file for every served set
    union = os.path.join(tempfile.gettempdir(), "d1_art_union")
    shutil.rmtree(union, ignore_errors=True)
    os.makedirs(union)
    n = 0
    for d in [ng.TEMPLATE] + glob.glob(os.path.join(ng.GUARDIANS, "*", "inventory")):
        for p in glob.glob(os.path.join(d, "*.bin")):
            shutil.copyfile(p, os.path.join(union, "%03d-%s" % (n, os.path.basename(p).split("-", 1)[1])))
            n += 1
    ng.run("art-arrangement", "write", "--inventory", union)
    ng.run("inventory", "rebuild", "--dir", inv, *nodes)
    # the rebuild leaves every weapon's talent nodes off (no perks at all): turn on a consistent
    # set - one node per exclusive set plus the set-less ones (talent_grid.default_active). Which
    # node of a set (e.g. Explosive Rounds) is not chosen yet: perk names are not resolved.
    for f in glob.glob(os.path.join(inv, "*Weapons.bin")):
        def activate(b):
            grid = struct.unpack_from("<H", b, 0x58)[0]
            if grid != 0xFFFF:
                for n in talent_grid.default_active(grid):
                    if n < 36:
                        b[0x5A + n] = 1
        ng.edit(ng.ELEMENT, f, activate)
    meta = dict(cls=1, race=0, gender=0, level=LEVEL, light=LIGHT, xp=400000, grid=grid[0], active=active,
                custom="00" * 32 + "01000000")   # the served Hunter's: all zero but wear-helmet (+0x20)
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"))
    ng.assemble(out, inv, meta)
    progress.write(name, progress.BASE + sorted(set(progress.COMPLETION.values()))
                   + progress.EXTRA[163])
    return out


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "hunter-custom"))

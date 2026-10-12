r"""Build the served objects for a Guardian from character-creation choices.

    python tools\new_guardian.py <name> --class 0|1|2 --race 0|1|2 --gender 0|1 [--custom <72 hex>]

class: 0 Titan, 1 Hunter, 2 Warlock (the game's own class byte). The customization block is
the 36 bytes the game sends in investment 501 (schema 0x8080181A: face, hair, markings,
colours, wear-helmet @+0x20) and is copied verbatim into the character, the profile and the
peer view at object +0x0C.

Writes capture-rig\guardians\<name>\{inventory\, char.bin, profile.bin, roster\} with
d1-oracle's builders. Gear: the class's upstream loadout (loadouts\y1-<class>-vault-of-glass
.json) with a spare Khvostov 7G-02 in the backpack; the class-neutral items (Ghost, sparrow,
ship, ...) are the served Hunter's. Item elements are minted from the served Hunter's elements
by changing the content index and letting `inventory rebuild` derive the rest.
NIGHT-NOTES section 66.
"""
import argparse
import glob
import json
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import finish_character as fc  # noqa: E402
import talent_grid  # noqa: E402

RIG = os.path.join(fc.REPO, "capture-rig")
TEMPLATE = os.path.join(RIG, "inventory-hunter-full")
GUARDIANS = os.path.join(RIG, "guardians")
CLASSES = {0: "titan", 1: "hunter", 2: "warlock"}
SLOT_FILE = {"subclass": "00-Subclass", "primary": "01-Primary Weapons", "special": "02-Special Weapons",
             "heavy": "03-Heavy Weapons", "head": "05-Helmet", "arms": "06-Gauntlets",
             "chest": "07-Chest Armor", "legs": "08-Leg Armor", "class_item": "09-Class Armor"}
SPARE = ("13-Primary Weapons", 3598)        # Khvostov 7G-02
ELEMENT, CHARACTER, PROFILE, PEER = "0x80801732", "0x80801954", "0x80801743", "0x808017FD"


def run(*a):
    r = fc.run(fc.ORACLE, *a)
    if r.returncode:
        raise SystemExit("d1-oracle %s: %s%s" % (" ".join(a[:2]), r.stdout[-500:], r.stderr[-500:]))
    return r.stdout


def edit(tag, path, fn, dst=None):
    """Decode an object file, let fn change the struct image, encode it back."""
    img = os.path.join(tempfile.gettempdir(), "d1_guardian.img")
    r = fc.run(fc.OBJFILE, "decode", tag, path, img)
    if r.returncode:
        raise SystemExit("decode %s: %s%s" % (path, r.stdout, r.stderr))
    b = bytearray(open(img, "rb").read())
    fn(b)
    open(img, "wb").write(b)
    r = fc.run(fc.OBJFILE, "encode", tag, img, dst or path)
    if r.returncode:
        raise SystemExit("encode %s: %s%s" % (dst or path, r.stdout, r.stderr))


def content_indices():
    rows = (l.split("\t") for l in open(os.path.join(RIG, "item-content-index.tsv"), encoding="utf-8", errors="replace")
            if l.startswith("0x"))
    return {int(h, 16): int(ci) for h, ci, _ in rows}


# What a new Guardian owns (content indices; the item table opens each class's armour block
# with its starter set - names from tools\game_strings.py items): Titan "Lightmail" + "Mark of
# the Risen", Hunter "Prototype 0.9" + "Makeshift Scarf", Warlock "Born Spark" + "Potential
# Bond"; subclass Striker / Gunslinger / Voidwalker; the Khvostov 7G-02; no special, no heavy,
# no sparrow. Ghost, ship, emote, shader and emblem are the served Hunter's.
STARTER = {
    0: {"Subclass": 710, "Helmet": 203, "Gauntlets": 197, "Chest Armor": 199, "Leg Armor": 205, "Class Armor": 201},
    1: {"Subclass": 709, "Helmet": 15, "Gauntlets": 9, "Chest Armor": 11, "Leg Armor": 17, "Class Armor": 13},
    2: {"Subclass": 713, "Helmet": 391, "Gauntlets": 385, "Chest Armor": 387, "Leg Armor": 393, "Class Armor": 389},
}
STARTER_ORDER = ["Subclass", "Primary Weapons", "Ghost", "Helmet", "Gauntlets", "Chest Armor", "Leg Armor",
                 "Class Armor", "Ships", "Emotes", "Shaders", "Emblems"]
BASE_SOID = 0xD100000000000301          # the element in file NN carries SOID BASE_SOID + NN


def stage(inv, items):
    """Write items = [(bucket, content index or None)] as element files 00.., from the served
    Hunter's element of the same bucket, each with the SOID its position requires."""
    os.makedirs(inv)
    for n, (bucket, ci) in enumerate(items):
        src = sorted(glob.glob(os.path.join(TEMPLATE, "*-%s.bin" % bucket)))[0]

        def set_item(b, n=n, ci=ci):
            struct.pack_into("<Q", b, 0, BASE_SOID + n)
            if ci is not None:
                struct.pack_into("<H", b, 0x24, ci)
        edit(ELEMENT, src, set_item, os.path.join(inv, "%02d-%s.bin" % (n, bucket)))


def build(name, cls, race, gender, custom=None, starter=True):
    out = os.path.join(GUARDIANS, name)
    inv = os.path.join(out, "inventory")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    if starter:
        level, light, xp = 1, 3, 0
        gear_items = dict(STARTER[cls], **{"Primary Weapons": SPARE[1]})
        stage(inv, [(b, gear_items.get(b)) for b in STARTER_ORDER])
    else:
        level, light, xp = 40, 385, 400000
        loadout = json.load(open(os.path.join(fc.REPO, "loadouts", "y1-%s-vault-of-glass.json" % CLASSES[cls]),
                                 encoding="utf-8"))
        ci_of = content_indices()
        items = {SLOT_FILE[e["slot"]]: ci_of[e["item"]["hash"]] for e in loadout["equipped"] if e["slot"] in SLOT_FILE}
        items[SPARE[0]] = SPARE[1]
        stage(inv, [(os.path.basename(p)[3:-4], items.get(os.path.basename(p)[:-4]))
                    for p in sorted(glob.glob(os.path.join(TEMPLATE, "*.bin")))])
    run("inventory", "rebuild", "--dir", inv, "--level", str(level))
    # the subclass's talent grid (the rebuild derives its index from the item) decides the
    # active nodes and the abilities: tools\talent_grid.py
    grid = []
    edit(ELEMENT, os.path.join(inv, "00-Subclass.bin"), lambda b: grid.append(struct.unpack_from("<H", b, 0x58)[0]))
    active = talent_grid.default_active(grid[0])
    nodes = ["--level", str(level), "--subclass-nodes", ",".join(str(n) for n in active)]
    run("inventory", "rebuild", "--dir", inv, *nodes)
    # the art table is one file for every served set: write it over all of them
    union = os.path.join(tempfile.gettempdir(), "d1_art_union")
    shutil.rmtree(union, ignore_errors=True)
    os.makedirs(union)
    n = 0
    for d in [TEMPLATE] + glob.glob(os.path.join(GUARDIANS, "*", "inventory")):
        for p in glob.glob(os.path.join(d, "*.bin")):
            shutil.copyfile(p, os.path.join(union, "%03d-%s" % (n, os.path.basename(p).split("-", 1)[1])))
            n += 1
    run("art-arrangement", "write", "--inventory", union)
    run("inventory", "rebuild", "--dir", inv, *nodes)
    gear = os.path.join(out, "inventory-gear")       # character / peer view refuse the emblem element
    shutil.copytree(inv, gear, ignore=lambda d, names: [x for x in names if "Emblems" in x])
    ident = "%d,%d,%d" % (race, gender, cls)
    char, prof, roster = os.path.join(out, "char.bin"), os.path.join(out, "profile.bin"), os.path.join(out, "roster")
    run("character", "build", "--inventory", gear, "--identity", ident, "--level", str(level),
        "--light", str(light), "--out", char)
    run("profile", "build", "--inventory", inv, "--identity", ident, "--all-content", "--light", str(light),
        "--progression", "117:%d" % xp, "--out", prof)
    run("character", "build-peer", "--inventory", gear, "--identity", ident, "--level", str(level),
        "--light", str(light), "--with-family2", "--out-dir", roster)
    shutil.rmtree(gear)
    peer = glob.glob(os.path.join(roster, "f0t1-*.bin"))[0]
    saved = fc.FILES, fc.ABILITIES
    fc.FILES = [(PEER, peer, 0x218), (CHARACTER, char, 0x250), (PROFILE, prof, None)]
    fc.ABILITIES = talent_grid.abilities(grid[0], active)
    try:
        fc.main()
    finally:
        fc.FILES, fc.ABILITIES = saved
    if custom:
        for tag, path in ((PEER, peer), (CHARACTER, char), (PROFILE, prof)):
            edit(tag, path, lambda b: b.__setitem__(slice(0x0C, 0x0C + 36), custom))
    return out


def env_lines(name):
    out = os.path.join(GUARDIANS, name)
    return ("D1_INVENTORY=%s\nD1_CHARACTER_FILE=%s\nD1_PROFILE_FILE=%s\nD1_ROSTER_DIR=%s\n"
            % (os.path.join(out, "inventory"), os.path.join(out, "char.bin"), os.path.join(out, "profile.bin"),
               os.path.join(out, "roster")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--class", dest="cls", type=int, required=True)
    ap.add_argument("--race", type=int, default=0)
    ap.add_argument("--gender", type=int, default=0)
    ap.add_argument("--custom", help="the 36-byte customization block, hex")
    ap.add_argument("--geared", action="store_true",
                    help="level 40 with the class's raid set instead of a level-1 starter")
    a = ap.parse_args()
    print(build(a.name, a.cls, a.race, a.gender, bytes.fromhex(a.custom) if a.custom else None, not a.geared))


if __name__ == "__main__":
    main()

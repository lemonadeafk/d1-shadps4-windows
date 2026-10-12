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


def build(name, cls, race, gender, custom=None):
    out = os.path.join(GUARDIANS, name)
    inv = os.path.join(out, "inventory")
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(TEMPLATE, inv)
    loadout = json.load(open(os.path.join(fc.REPO, "loadouts", "y1-%s-vault-of-glass.json" % CLASSES[cls]),
                             encoding="utf-8"))
    ci_of = content_indices()
    items = {SLOT_FILE[e["slot"]]: ci_of[e["item"]["hash"]] for e in loadout["equipped"] if e["slot"] in SLOT_FILE}
    items[SPARE[0]] = SPARE[1]
    for stem, ci in items.items():
        def set_item(b, ci=ci, stem=stem):
            struct.pack_into("<H", b, 0x24, ci)
            if stem == "00-Subclass" and cls != 1:
                b[0x5A:0x5A + 36] = bytes(36)     # talent nodes off: the served set is Bladedancer's
        edit(ELEMENT, os.path.join(inv, stem + ".bin"), set_item)
    run("inventory", "rebuild", "--dir", inv)
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
    run("inventory", "rebuild", "--dir", inv)
    gear = os.path.join(out, "inventory-gear")       # character / peer view refuse the emblem element
    shutil.copytree(inv, gear, ignore=lambda d, names: [x for x in names if "Emblems" in x])
    ident = "%d,%d,%d" % (race, gender, cls)
    char, prof, roster = os.path.join(out, "char.bin"), os.path.join(out, "profile.bin"), os.path.join(out, "roster")
    run("character", "build", "--inventory", gear, "--identity", ident, "--out", char)
    run("profile", "build", "--inventory", inv, "--identity", ident, "--all-content",
        "--progression", "117:400000", "--out", prof)
    run("character", "build-peer", "--inventory", gear, "--identity", ident, "--with-family2", "--out-dir", roster)
    shutil.rmtree(gear)
    peer = glob.glob(os.path.join(roster, "f0t1-*.bin"))[0]
    saved = fc.FILES, fc.ABILITIES
    fc.FILES = [(PEER, peer, 0x218), (CHARACTER, char, 0x250), (PROFILE, prof, None)]
    if cls != 1:
        fc.ABILITIES = None         # the ability rows in finish_character are the Bladedancer's
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
    a = ap.parse_args()
    print(build(a.name, a.cls, a.race, a.gender, bytes.fromhex(a.custom) if a.custom else None))


if __name__ == "__main__":
    main()

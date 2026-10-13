r"""Build a variant of the served Hunter's weapons, for a mid-session loadout change.

    python tools\loadout_variant.py <name> [--primary CI] [--special CI|none] [--heavy CI|none]
                                           [--unarmed]

Writes capture-rig\variants\<name>\char.bin (character, family 3) and
capture-rig\variants\<name>\roster\ (peer view, family 0) from the served Hunter, with the
weapon equipment entries changed: {u64 SOID, u16 content index @+8, u16 pattern @+0x0A,
u16 art index @+0x0C}. The pattern (what makes the weapon work) and the art index (its model)
are read from the item's definition. "none" / --unarmed empties the slot's working data
(pattern 0 = the weapon object exists but is dead: open hand, no weapon HUD).

The login server pushes a variant to the running game when its D1_SWAP_TRIGGER file appears
(tools\mission_director.py step "loadout"). NIGHT-NOTES section 63.
"""
import argparse
import os
import re
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import finish_character as fc  # noqa: E402

VARIANTS = os.path.join(fc.REPO, "capture-rig", "variants")
ORDINALS = {"primary": 6, "special": 7, "heavy": 8}
KHVOSTOV = 3598      # "Khvostov 7G-02", item hash 0x1cba8a98 (tools\game_strings.py items)


def art_of(ci):
    out = fc.run(fc.ORACLE, "art-arrangement", "show", "--index", str(ci)).stdout
    m = re.search(r"entries \[\((-?\d+), (\d+)\)", out)
    return int(m.group(2)) if m else None


def build(name, slots):
    """slots: {"primary": content index | None (dead) | absent (unchanged)}"""
    out = os.path.join(VARIANTS, name)
    roster = os.path.join(out, "roster")
    if os.path.isdir(roster):
        shutil.rmtree(roster)
    os.makedirs(out, exist_ok=True)
    files = list(fc.FILES[:2])
    import new_guardian
    cur = new_guardian.current()
    if cur:             # a Guardian made in the creator is being served: vary THAT one
        peer = os.path.basename(fc.FILES[0][1])
        files = [(fc.FILES[0][0], os.path.join(cur[1], "roster", peer), fc.FILES[0][2]),
                 (fc.FILES[1][0], os.path.join(cur[1], "char.bin"), fc.FILES[1][2])]
    src_roster = os.path.join(fc.REPO, os.path.dirname(files[0][1]))
    shutil.copytree(src_roster, roster)
    targets = [(files[0], os.path.join(roster, os.path.basename(files[0][1]))),
               (files[1], os.path.join(out, "char.bin"))]
    img = os.path.join(tempfile.gettempdir(), "d1_variant.img")
    for (tag, rel, equip), dst in targets:
        r = fc.run(fc.OBJFILE, "decode", tag, os.path.join(fc.REPO, rel), img)
        if r.returncode:
            raise SystemExit("decode %s: %s%s" % (rel, r.stdout, r.stderr))
        b = bytearray(open(img, "rb").read())
        for slot, ci in slots.items():
            e = equip + ORDINALS[slot] * 0x40
            if ci is None:
                struct.pack_into("<H", b, e + 0x0A, 0)
                continue
            if ci == "empty":
                # nothing equipped: the exact form of an unused slot in the served character
                # (ordinals 17-19): SOID 0, content index 0xFFFF, the rest "unset"
                b[e:e + 0x40] = bytes.fromhex("00000000000000" "00" "ffff0000" + "ff" * 16 + "ffff0000") + bytes(0x40 - 0x20)
                continue
            pattern, art = fc.pattern_of(ci), art_of(ci)
            if pattern is None or art is None:
                raise SystemExit("content index %d: no pattern / art in its definition" % ci)
            struct.pack_into("<HHH", b, e + 8, ci, pattern, art)
            k = ORDINALS[slot] - 6                  # this weapon's stats (finish_character 4.)
            for n, (idx, val) in enumerate(fc.weapon_stats(ci) or []):
                struct.pack_into("<bxxxi", b, equip + 0x6A0 + k * 0x80 + n * 8, idx, val)
        open(img, "wb").write(b)
        r = fc.run(fc.OBJFILE, "encode", tag, img, dst)
        if r.returncode:
            raise SystemExit("encode %s: %s%s" % (dst, r.stdout, r.stderr))
    return out


def swap_lines(name):
    """The D1_SWAP_TRIGGER file contents that push this variant."""
    out = os.path.join(VARIANTS, name)
    return "D1_ROSTER_DIR=%s\nD1_CHARACTER_FILE=%s\nFAMILIES=0,3\n" % (
        os.path.join(out, "roster"), os.path.join(out, "char.bin"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--primary")
    ap.add_argument("--special")
    ap.add_argument("--heavy")
    ap.add_argument("--unarmed", action="store_true")
    ap.add_argument("--empty", action="store_true", help="with --unarmed: slots EMPTY instead of dead")
    a = ap.parse_args()
    slots = {}
    for slot in ORDINALS:
        v = getattr(a, slot)
        if v == "empty" or (a.unarmed and a.empty):
            slots[slot] = "empty"
        elif a.unarmed or v == "none":
            slots[slot] = None
        elif v:
            slots[slot] = int(v, 0)
    print(build(a.name, slots))


if __name__ == "__main__":
    main()

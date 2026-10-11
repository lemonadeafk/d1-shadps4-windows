r"""Finish the served Hunter after d1-oracle's builders: the fields they do not set yet.

    python tools\finish_character.py            (run after character build / build-peer / profile build)

1. wear-helmet: customization +0x20 (object +0x2C) = 1 in character, peer view and profile.
2. WEAPON PATTERN: equipment entry +0x0A (u16) for the three weapon ordinals (6, 7, 8) in the
   character (0x80801954, entries at +0x250) and the peer view (0x808017FD, entries at +0x218).
   The client's weapon-description builder FUN_0090EFD0 looks that index up in the pattern
   table (investment-globals root +0x350, 192 rows x 0x20 = {asset key, hash, type hash, ..})
   and copies the row's hashes and gameplay bundle. 0 = a blank default: the weapon object is
   created but dead (open hand + Ghost, no firing). The value is CONTENT: the u32 at
   gear record +0x60 of the item definition (The Last Word 32, Praedyth's Revenge 13,
   Corrective Measure 14). Found 2026-10-11, NIGHT-NOTES section 42.
"""
import os, re, struct, subprocess, tempfile

REPO = r"C:\d1server\d1preservation"
ORACLE = os.path.join(REPO, r"d1-server\target\release\d1-oracle.exe")
OBJFILE = os.path.join(REPO, r"d1-server\target\release\examples\object_file.exe")
FILES = [  # schema tag, file, equipment array offset (None = no equipment entries)
    ("0x808017FD", r"capture-rig\rosters-f0-hunter\f0t1-d100000000000501.bin", 0x218),
    ("0x80801954", r"capture-rig\characters\char-hunter.bin", 0x250),
    ("0x80801743", r"capture-rig\profiles\profile-hunter.bin", None),
]
WEAPON_ORDINALS = (6, 7, 8)
# Bladedancer (talent grid 130) with the served node set 0,1,2,3,4,7,10,12,13,19,20,23,24,25.
# Read from the grid definition: each node carries 0x808018E8 elements {option hash, u8 target
# row @+4, u8 ability row @+0xB, u32 slot @+0xC} and a 0x80804628 list of perk indices
# (scratchpad grid3.py; NIGHT-NOTES section 43). slot 0 grenade (node 1), 1 (node 19),
# 2 (node 25), 3 (node 0), 4 (node 12); node 13 also names slot 0 (row 1) - the grenade wins.
ABILITIES = {
    "slots": [
        (26, []),
        (12, [0x9D0FA163, 0xD2B26EC9]),
        (8, [0x62239B90, 0xD2B26EC9, 0xD4D0F628]),
        (3, []),
        (13, []),
    ],
    "perks": [208, 88, 89, 84, 76, 77, 78, 79],
}
if os.environ.get("D1_ABILITIES") == "off":
    ABILITIES = None


def run(*a):
    return subprocess.run(a, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")


def pattern_of(content_index):
    """gear record +0x60 of the item's definition, or None."""
    out = run(ORACLE, "art-arrangement", "show", "--index", str(content_index)).stdout
    m = re.search(r"tag (0x[0-9a-f]+).*gear @\+(0x[0-9a-f]+)", out)
    if not m:
        return None
    tmp = os.path.join(tempfile.gettempdir(), "d1_def_%s.bin" % m.group(1))
    run(ORACLE, "oodle", "entry", "--tag", m.group(1), "-o", tmp)
    b = open(tmp, "rb").read()
    off = int(m.group(2), 16) + 0x60
    return struct.unpack_from("<I", b, off)[0] if off + 4 <= len(b) else None


def main():
    img = os.path.join(tempfile.gettempdir(), "d1_finish.img")
    cache = {}
    for tag, rel, equip in FILES:
        path = os.path.join(REPO, rel)
        r = run(OBJFILE, "decode", tag, path, img)
        if r.returncode:
            raise SystemExit(f"decode {rel}: {r.stdout}{r.stderr}")
        b = bytearray(open(img, "rb").read())
        b[0x2C] = 1
        if equip is not None and ABILITIES:
            # 3. ABILITIES: 5 x {u8 ability-table row, 16 option hashes} at appearance block +0x10
            #    (= equipment array - 0x1D8) and 32 x u16 perk indices at block +0x768.
            #    FUN_0090E000 resolves the row in the 38-row ability table (root +0x340) to a
            #    bundle and applies the option hashes; 0xFF rows assert at spawn. Zeros (what
            #    the builders ship) = row 0 five times = no sprint/grenade/melee, wrong super.
            blk = equip - 0x1D8
            for slot, (row, opts) in enumerate(ABILITIES["slots"]):
                e = blk + slot * 68
                b[e] = row
                hashes = (list(opts) + [0x811C9DC5] * 16)[:16]
                struct.pack_into("<16I", b, e + 4, *hashes)
            perks = (list(dict.fromkeys(ABILITIES["perks"])) + [0xFFFF] * 32)[:32]
            struct.pack_into("<32H", b, equip - 0x1E8 + 0x768, *perks)
            print(f"  {os.path.basename(rel)}: ability rows {[r for r, _ in ABILITIES['slots']]}, "
                  f"{sum(1 for x in perks if x != 0xFFFF)} perks")
        if equip is not None:
            for o in WEAPON_ORDINALS:
                e = equip + o * 0x40
                soid, ci = struct.unpack_from("<QH", b, e)
                if not soid or ci == 0xFFFF:
                    continue
                if ci not in cache:
                    cache[ci] = pattern_of(ci)
                p = cache[ci]
                if p is None or p > 0xFFFE:
                    print(f"  {rel}: ordinal {o} content index {ci}: no pattern in the definition")
                    continue
                struct.pack_into("<H", b, e + 0x0A, p)
                print(f"  {os.path.basename(rel)}: ordinal {o} content index {ci} -> pattern {p}")
        open(img, "wb").write(b)
        r = run(OBJFILE, "encode", tag, img, path)
        print(f"{rel}: {r.stdout.strip()[:70]}")


if __name__ == "__main__":
    main()

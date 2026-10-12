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


def weapon_stats(content_index):
    """The 16 x {i8 stat index, i32 value} the game expects for a weapon, or None.

    The item definition lists its stats (0x8080190C: {u32 index, u32 value} pairs); the game's
    own character-screen preview (FUN_0054EB40 -> FUN_0090EFD0, captured 2026-10-12) sends the
    non-zero ones sorted by index, after two instance stats: 11 = attack and 0. For the
    level-40 items served here attack = 200 + the definition's curve offset and stat 0 =
    attack / 10 + 5 (fitted to The Last Word 270 / 32 and Praedyth's Revenge 260 / 31 only).
    """
    out = run(ORACLE, "art-arrangement", "show", "--index", str(content_index)).stdout
    m = re.search(r"tag (0x[0-9a-f]+)", out)
    if not m:
        return None
    tmp = os.path.join(tempfile.gettempdir(), "d1_def_%s.bin" % m.group(1))
    run(ORACLE, "oodle", "entry", "--tag", m.group(1), "-o", tmp)
    b = open(tmp, "rb").read()
    at = b.find(bytes.fromhex("0c198080"))
    if at < 8:
        return None
    count = struct.unpack_from("<Q", b, at - 8)[0]
    pairs = [struct.unpack_from("<II", b, at + 8 + k * 8) for k in range(min(count, 32))]
    curve = re.search(r"curve \(true, (\d+)\)", out)
    attack = 200 + int(curve.group(1)) if curve else 200
    stats = {0: attack // 10 + 5, 11: attack}
    stats.update({i: v for i, v in pairs if v and i not in (0, 11)})
    rows = sorted(stats.items())[:16]
    return rows + [(-1, 0)] * (16 - len(rows))


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
                # 4. WEAPON STATS and perks (NIGHT-NOTES section 68): per weapon 16 x u16 perk
                #    indices at equip + 0x5C0 and 16 x {i8 stat, i32 value} at equip + 0x6A0.
                #    Zeros = sixteen copies of "stat 0 = 0": a 3-round magazine on everything.
                k = o - WEAPON_ORDINALS[0]
                stats = weapon_stats(ci)
                if stats:
                    struct.pack_into("<16H", b, equip + 0x5C0 + k * 0x20, *([0xFFFF] * 16))
                    for n, (idx, val) in enumerate(stats):
                        struct.pack_into("<bxxxi", b, equip + 0x6A0 + k * 0x80 + n * 8, idx, val)
                    print(f"  {os.path.basename(rel)}: ordinal {o} stats {[s for s in stats if s[0] >= 0]}")
        open(img, "wb").write(b)
        r = run(OBJFILE, "encode", tag, img, path)
        print(f"{rel}: {r.stdout.strip()[:70]}")


if __name__ == "__main__":
    main()

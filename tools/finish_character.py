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

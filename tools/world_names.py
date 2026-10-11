r"""Rebuild the world/activity name list from the game's own packages (symbol tables).

    python tools\world_names.py [filter]      -> capture\world-namespace.tsv (not tracked)

Each content package header has a symbol table: count at +0xEC, offset at +0xF0, records of
0x44 bytes {u32 tag, u32 type tag, char name[0x3C]}. The top-level (colon-free) names are the
ACTIVITY symbols the activity host publishes; FNV-1 32 of the name is the world record's +0x08.
"""
import glob
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fnv1(s):
    h = 0x811C9DC5
    for c in s.encode():
        h = ((h * 0x01000193) & 0xFFFFFFFF) ^ c
    return h


def symbols(path):
    with open(path, "rb") as f:
        hdr = f.read(0x100)
        if len(hdr) < 0x100:
            return
        n, off = struct.unpack_from("<II", hdr, 0xEC)
        if not 0 < n < 100000:
            return
        f.seek(off)
        blob = f.read(n * 0x44)
    for i in range(len(blob) // 0x44):
        tag, ttag = struct.unpack_from("<II", blob, i * 0x44)
        name = blob[i * 0x44 + 8:i * 0x44 + 0x44].split(b"\0")[0].decode("latin1")
        if name:
            yield tag, ttag, name


def main():
    flt = sys.argv[1].lower() if len(sys.argv) > 1 else None
    pkgs = []
    for d in ("CUSA00219-129", "CUSA00219-UPDATE"):
        pkgs += glob.glob(os.path.join(ROOT, d, "**", "*.pkg"), recursive=True)
    # A package ships in several patch versions (.._0.pkg, .._3.pkg); tags are per version and the
    # game resolves the NEWEST, so the highest suffix wins (the update folder breaks ties).
    def version(p):
        stem = os.path.basename(p)[:-4]
        tail = stem.rsplit("_", 1)[-1]
        return (int(tail) if tail.isdigit() else 0, "UPDATE" in p)

    rows, best = {}, {}
    for p in sorted(pkgs):
        v = version(p)
        for tag, ttag, name in symbols(p):
            if name not in rows or v >= best[name]:
                rows[name], best[name] = (tag, ttag, os.path.basename(p)), v
    out = os.path.join(ROOT, "capture", "world-namespace.tsv")
    with open(out, "w", newline="\n") as f:
        f.write("# name\tfnv1\ttag\ttype_tag\tpackage\n")
        for name in sorted(rows):
            tag, ttag, pkg = rows[name]
            f.write(f"{name}\t0x{fnv1(name):08x}\t0x{tag:08x}\t0x{ttag:08x}\t{pkg}\n")
    print(len(pkgs), "packages,", len(rows), "names ->", out)
    if flt:
        for name in sorted(rows):
            if flt in name.lower() and ":" not in name:
                tag, ttag, pkg = rows[name]
                print(f"{name:44s} 0x{fnv1(name):08x} tag 0x{tag:08x} type 0x{ttag:08x} {pkg}")


if __name__ == "__main__":
    main()

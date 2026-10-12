r"""Dump the game's text from its package files (the user's own 01.29 dump).

    python tools\game_strings.py <package name substring> [...]  [--out strings.tsv]

Text lives in "string bank" entries (class 0x808008BE): a list of parts
{i64 self-relative data offset @+8, u32 hash @+0x10, u16 byte length, u16 char length,
u16 key} (0x20 bytes each, count at +0x60, first part at +0x70); each UTF-8 byte is stored
minus `key`. Blocks are decompressed with d1-oracle (the client's own decoder) and cached.
Output: package, entry tag, part index, text. NIGHT-NOTES section 64.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile

REPO = r"C:\d1server\d1preservation"
BIN = os.path.join(REPO, r"d1-server\target\release")
PKGS = os.path.join(REPO, r"dumps\patch-01.29-CUSA00219\packages")
BANK = "808008be"
CACHE = os.path.join(tempfile.gettempdir(), "d1-blocks")


def entries(pkg):
    out = subprocess.run([os.path.join(BIN, "d1-pkg.exe"), "entries", pkg], capture_output=True, text=True).stdout
    for line in out.splitlines():
        p = line.split()
        if len(p) > 12 and p[0] == "idx":
            yield dict(tag=p[3], cls=p[5], blk=int(p[p.index("blk") + 1]), off=int(p[p.index("off") + 1]),
                       size=int(p[p.index("size") + 1]))


def block(pkg, n):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "%s.%d" % (pkg, n))
    if not os.path.exists(path):
        subprocess.run([os.path.join(BIN, "d1-oracle.exe"), "oodle", "block", "--pkg", pkg, "--block", str(n),
                        "-o", path], capture_output=True)
    return open(path, "rb").read() if os.path.exists(path) else b""


def payload(pkg, e):
    data, n = b"", e["blk"]
    need = e["off"] + e["size"]
    while len(data) < need:
        b = block(pkg, n)
        if not b:
            return b""
        data += b
        n += 1
    return data[e["off"]:need]


def parts(b):
    if len(b) < 0x70:
        return
    count = struct.unpack_from("<Q", b, 0x60)[0]
    for i in range(count):
        e = 0x70 + i * 0x20
        if e + 0x20 > len(b):
            return
        rel = struct.unpack_from("<q", b, e + 8)[0]
        _, nbytes, _, key = struct.unpack_from("<IHHH", b, e + 0x10)
        p = e + 8 + rel
        raw = bytes((c + key) & 0xFF for c in b[p:p + nbytes])
        yield i, raw.decode("utf-8", "replace")


CONTAINER = "8080035a"          # string container: language bank tags + a hash list
DISPLAY = "80803484"            # per-item display record: {u32 container index, u32 hash} @+0x78 = name
ITEM_INDEX = os.path.join(REPO, "capture-rig", "item-content-index.tsv")
ITEM_NAMES = os.path.join(REPO, "capture-rig", "item-names.tsv")
ROOT_PKG = "ps4_investment_globals_012f_3.pkg"


def _list_after(header, stride, count, tag_at):
    """Tags of a list found by its {u64 count, u32 element class, u32 0} header in ROOT_PKG."""
    info = subprocess.run([os.path.join(BIN, "d1-pkg.exe"), "info", ROOT_PKG], capture_output=True, text=True).stdout
    nblocks = int(info.split("blocks")[1].split()[0])
    for n in range(nblocks):
        b = block(ROOT_PKG, n)
        i = b.find(header)
        if i < 0:
            continue
        data = b[i + len(header):] + block(ROOT_PKG, n + 1)
        return ["%08x" % struct.unpack_from("<I", data, r * stride + tag_at)[0] for r in range(count)]
    raise SystemExit("list header %s not found" % header.hex())


def item_names():
    """Write capture-rig\\item-names.tsv: content index, item hash, English name.

    item (content index) -> display record: list 0x808033E8 (7544 x 16 B, one tag per content
    index) in the investment-globals root; display record +0x78 = {container index, hash};
    container index -> container tag: list 0x80803473 (817 x 24 B, tag @+0x10); container =
    {u64 size, u64 count, .., 13 language bank tags @+0x18 (English first), count x u32 hash at
    the end}; the hash's position is the part index in the bank.
    """
    pk = sorted(n for n in os.listdir(PKGS) if "investment_globals" in n)
    where = {}
    for p in pk:                                  # later patch packages override earlier ones
        for e in entries(p):
            where[e["tag"]] = (p, e)
    text = {}
    for t, (p, e) in where.items():
        if e["cls"] != CONTAINER:
            continue
        b = payload(p, e)
        n = struct.unpack_from("<Q", b, 8)[0]
        bank = "%08x" % struct.unpack_from("<I", b, 0x18)[0]
        if bank not in where or n == 0:
            continue
        strings = dict(parts(payload(*where[bank])))
        for i, h in enumerate(struct.unpack_from("<%dI" % n, b, len(b) - 4 * n)):
            if i in strings:
                text[(t, h)] = strings[i]
    containers = _list_after(struct.pack("<QII", 817, 0x80803473, 0), 24, 817, 16)
    rows = [l.split("\t") for l in open(ITEM_INDEX, encoding="utf-8", errors="replace") if l.startswith("0x")]
    display = _list_after(struct.pack("<QII", len(rows), 0x808033E8, 0), 16, len(rows), 8)
    named = 0
    with open(ITEM_NAMES, "w", encoding="utf-8") as out:
        out.write("content_index\titem_hash\tname\n")
        for h, ci, _ in rows:
            name = ""
            if display[int(ci)] in where:
                d = payload(*where[display[int(ci)]])
                if len(d) >= 0x80:
                    idx, nh = struct.unpack_from("<II", d, 0x78)
                    if idx < len(containers):
                        name = text.get((containers[idx], nh), "")
            named += bool(name)
            out.write("%s\t%s\t%s\n" % (ci, h, name.strip()))
    print(named, "of", len(rows), "items named ->", ITEM_NAMES)


def main():
    if sys.argv[1:2] == ["items"]:
        return item_names()
    ap = argparse.ArgumentParser()
    ap.add_argument("packages", nargs="+")
    ap.add_argument("--out", default="strings.tsv")
    a = ap.parse_args()
    names = sorted(n for n in os.listdir(PKGS) if any(s in n for s in a.packages))
    total = 0
    with open(a.out, "w", encoding="utf-8") as out:
        for pkg in names:
            banks = [e for e in entries(pkg) if e["cls"] == BANK]
            for e in banks:
                for i, text in parts(payload(pkg, e)):
                    out.write("%s\t%s\t%d\t%s\n" % (pkg, e["tag"], i, text.replace("\n", "\\n").replace("\t", " ")))
                    total += 1
            print(pkg, len(banks), "banks", flush=True)
    print(total, "strings ->", a.out)


if __name__ == "__main__":
    main()

r"""Answer the game's "equip this item" requests (investment 403) for the served Hunter.

    python tools\equip_service.py                 watch the newest run and answer its requests
    python tools\equip_service.py --equip 0xD10000000000030E    build the result only (no game)

The login server logs each request ("EQUIP REQUEST 403 body <hex>": the bit-packed item
SOID). For that item this rebuilds the three objects that say what is equipped - character
(family 3), peer view (family 0), profile (family 4) - with d1-oracle's own builders from a
VIEW of the served inventory in which the requested item sorts first in its bucket (the
builders treat the first item of a bucket as the equipped one), finishes them
(tools\finish_character.py: weapon patterns, abilities, helmet) and hands them to the login
server through its D1_SWAP_TRIGGER file; the server pushes them as deltas and the game
re-equips. The item elements themselves (family 4/3, D1_INVENTORY) keep their SOIDs and are
not touched. NIGHT-NOTES section 65.
"""
import argparse
import glob
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import finish_character as fc  # noqa: E402
import new_guardian  # noqa: E402

RIG = os.path.join(fc.REPO, "capture-rig")
INVENTORY = os.path.join(RIG, "inventory-hunter-full")
LIVE = os.path.join(RIG, "variants", "live")
BASE_SOID = 0xD100000000000301          # element file NN carries SOID BASE_SOID + NN
SWAP_TRIGGER = os.path.join(os.path.dirname(HERE), "inject", "loadout-swap.txt")
ORDER = os.path.join(LIVE, "equipped.txt")   # the SOIDs equipped so far, one per line


def served():
    """(inventory folder, created Guardian or None): what the launcher is serving."""
    cur = new_guardian.current()
    return (os.path.join(cur[1], "inventory"), cur) if cur else (INVENTORY, None)


def elements():
    """{file index: (bucket name, path)} of the served inventory."""
    out = {}
    for p in sorted(glob.glob(os.path.join(served()[0], "*.bin"))):
        m = re.match(r"(\d+)-(.+)\.bin$", os.path.basename(p))
        if m:
            out[int(m.group(1))] = (m.group(2), p)
    return out


def view(equipped):
    """A copy of the inventory where each equipped item is the first of its bucket."""
    el = elements()
    first = {}
    for n in sorted(el):
        first.setdefault(el[n][0], n)
    names = {n: n for n in el}
    for soid in equipped:
        n = soid - BASE_SOID
        if n not in el:
            raise SystemExit("no served item has SOID %#x" % soid)
        head = first[el[n][0]]
        holder = next(k for k, v in names.items() if v == head)     # who sits first now
        names[holder], names[n] = names[n], head
    cur = served()[1]
    dst = os.path.join(cur[1] if cur else LIVE, "view")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for n, (bucket, path) in el.items():
        shutil.copyfile(path, os.path.join(dst, "%02d-%s.bin" % (names[n], bucket)))
    return dst


def run(*a):
    r = fc.run(fc.ORACLE, *a)
    if r.returncode:
        raise SystemExit("d1-oracle %s: %s%s" % (" ".join(a[:2]), r.stdout[-400:], r.stderr[-400:]))
    return r.stdout


def build(equipped, out=None):
    """Rebuild character / peer view / profile with `equipped` (SOIDs) worn; returns the folder.

    The slow, from-scratch way (about 10 s): tools\\fast_equip.py uses it once per spare item
    to learn that item's equipment data, and it is the fallback for an item not learned yet."""
    os.makedirs(LIVE, exist_ok=True)
    full = view(equipped)
    cur = served()[1]
    if cur:         # a Guardian made in the creator: rebuilt in place, so the change is kept
        out = out or cur[1]
        os.makedirs(out, exist_ok=True)
        new_guardian.assemble(out, os.path.join(cur[1], "inventory"), cur[2], full)
        return out
    # character and peer view refuse the emblem element (they take the emblem via --emblem)
    gear = os.path.join(LIVE, "view-gear")
    if os.path.isdir(gear):
        shutil.rmtree(gear)
    shutil.copytree(full, gear, ignore=lambda d, names: [n for n in names if "Emblems" in n])
    char, prof, roster = (os.path.join(LIVE, "char.bin"), os.path.join(LIVE, "profile.bin"),
                          os.path.join(LIVE, "roster"))
    if os.path.isdir(roster):
        shutil.rmtree(roster)
    run("character", "build", "--inventory", gear, "--identity", "0,0,1", "--out", char)
    run("profile", "build", "--inventory", full, "--identity", "0,0,1", "--all-content",
        "--progression", "117:400000", "--out", prof)
    if os.environ.get("EQUIP_SLOTS") != "move":
        # The items KEEP their inventory slots; only the equipped list (20 SOIDs at +0x2B80,
        # indexed by equip ordinal) changes. Moving the two items between slots made the game
        # announce both as newly acquired (section 65). So: the profile built from the served
        # order, with the equipped list of the one built from the view.
        import tempfile
        img_view = os.path.join(tempfile.gettempdir(), "d1_equip_view.img")
        img = os.path.join(tempfile.gettempdir(), "d1_equip.img")
        fc.run(fc.OBJFILE, "decode", "0x80801743", prof, img_view)
        run("profile", "build", "--inventory", INVENTORY, "--identity", "0,0,1", "--all-content",
            "--progression", "117:400000", "--out", prof)
        fc.run(fc.OBJFILE, "decode", "0x80801743", prof, img)
        b = bytearray(open(img, "rb").read())
        b[0x2B80:0x2B80 + 160] = open(img_view, "rb").read()[0x2B80:0x2B80 + 160]
        open(img, "wb").write(b)
        r = fc.run(fc.OBJFILE, "encode", "0x80801743", img, prof)
        if r.returncode:
            raise SystemExit("encode profile: %s%s" % (r.stdout, r.stderr))
    run("character", "build-peer", "--inventory", gear, "--identity", "0,0,1", "--with-family2",
        "--out-dir", roster)
    peer = glob.glob(os.path.join(roster, "f0t1-*.bin"))[0]
    saved = fc.FILES
    fc.FILES = [("0x808017FD", peer, 0x218), ("0x80801954", char, 0x250), ("0x80801743", prof, None)]
    try:
        fc.main()
    finally:
        fc.FILES = saved
    with open(ORDER, "w") as f:
        f.write("".join("%#x\n" % s for s in equipped))
    return LIVE


def swap_lines():
    cur = served()[1]
    if cur:
        return new_guardian.env_lines(cur[0]) + "FAMILIES=0,3,4\n"
    return ("D1_ROSTER_DIR=%s\nD1_CHARACTER_FILE=%s\nD1_PROFILE_FILE=%s\nFAMILIES=0,3,4\n"
            % (os.path.join(LIVE, "roster"), os.path.join(LIVE, "char.bin"), os.path.join(LIVE, "profile.bin")))


def soid_of(body_hex):
    """The item SOID in a 403 request body: 64 bits at some bit offset, high bytes D1 00 00."""
    bits = bin(int(body_hex, 16))[2:].zfill(len(body_hex) * 4)
    for i in range(0, len(bits) - 63):
        v = int(bits[i:i + 64], 2)
        if v >> 40 == 0xD10000 and v - BASE_SOID in elements():
            return v
    return None


def newest_run():
    runs = sorted(glob.glob(os.path.join(fc.REPO, "runs", "*WIN-*")), key=os.path.getmtime)
    return runs[-1] if runs else None


def watch():
    run_dir = newest_run()
    log = os.path.join(run_dir, "responder.log")
    print("watching", log, flush=True)
    equipped = []
    offset = 0
    fast = None
    try:                    # the quick way (tools\fast_equip.py); the rebuild below still works without it
        import threading
        import fast_equip
        fast = fast_equip.Fast()
        threading.Thread(target=fast.warm, daemon=True).start()
    except (SystemExit, Exception) as e:
        print("fast path unavailable:", e, flush=True)
    while True:
        if newest_run() != run_dir:
            return
        try:
            with open(log, "rb") as f:
                f.seek(offset)
                data = f.read()
        except OSError:
            data = b""
        end = data.rfind(b"\n") + 1
        offset += end
        for line in data[:end].decode("utf-8", "replace").splitlines():
            m = re.search(r"EQUIP REQUEST 403 body ([0-9a-f]+)", line)
            if not m:
                continue
            soid = soid_of(m.group(1))
            if soid is None:
                print(time.strftime("%H:%M:%S"), "equip request not understood:", m.group(1), flush=True)
                continue
            bucket = elements()[soid - BASE_SOID][0]
            equipped = [s for s in equipped if elements()[s - BASE_SOID][0] != bucket] + [soid]
            t0 = time.time()
            lines, how = (fast.equip(soid) if fast else None), "patched"
            if lines is None:
                build(equipped)
                lines, how = swap_lines(), "rebuilt"
            for stale in (SWAP_TRIGGER, os.path.splitext(SWAP_TRIGGER)[0] + ".done"):
                if os.path.exists(stale):
                    os.remove(stale)
            with open(SWAP_TRIGGER + ".tmp", "w") as f:
                f.write(lines)
            os.replace(SWAP_TRIGGER + ".tmp", SWAP_TRIGGER)
            print(time.strftime("%H:%M:%S"), "equipped %#x (%s) - %s in %.1f s" % (soid, bucket, how, time.time() - t0), flush=True)
            t1 = time.time()            # the login server takes the file on the game's next keepalive
            while os.path.exists(SWAP_TRIGGER) and time.time() - t1 < 15:
                time.sleep(0.05)
            print(time.strftime("%H:%M:%S"), "pushed %.1f s later" % (time.time() - t1), flush=True)
        time.sleep(0.1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equip", action="append", help="build with this SOID equipped and exit")
    a = ap.parse_args()
    if a.equip:
        print(build([int(s, 0) for s in a.equip]))
        return
    watch()


if __name__ == "__main__":
    main()

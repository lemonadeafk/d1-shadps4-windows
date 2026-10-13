r"""Equip by PATCHING the served objects instead of rebuilding them (about 1 s instead of 10).

An equip changes three things: the item's 0x40-byte equipment entry in the character
(0x80801954, entries at +0x250) and in the peer view (0x808017FD, +0x218) - plus, for a weapon,
its perk block (equip + 0x5C0 + k*0x20) and stat block (equip + 0x6A0 + k*0x80) - and one SOID
in the profile's equipped list (0x80801743 +0x2B80, 20 x u64 by equip ordinal).

The decoded objects are kept in memory. Each item's entry and blocks are taken from an object
in which it is worn: the served one for what is equipped now, and one slow build per spare
(warm(), run in the background when tools\equip_service.py starts). An item that has not been
learned yet falls back to the slow rebuild. NIGHT-NOTES section 73.
"""
import glob
import os
import shutil
import struct
import tempfile
import threading
import time

import finish_character as fc

CHAR, PEER, PROF = ("0x80801954", 0x250), ("0x808017FD", 0x218), ("0x80801743", None)
EQUIPPED_LIST = 0x2B80
WEAPONS = (6, 7, 8)


def _decode(tag, path):
    img = os.path.join(tempfile.gettempdir(), "d1_fast_%d_%d.img" % (os.getpid(), threading.get_ident()))
    r = fc.run(fc.OBJFILE, "decode", tag, path, img)
    if r.returncode:
        raise SystemExit("decode %s: %s%s" % (path, r.stdout, r.stderr))
    return bytearray(open(img, "rb").read())


def _encode(tag, image, path):
    img = os.path.join(tempfile.gettempdir(), "d1_fast_%d_%d.img" % (os.getpid(), threading.get_ident()))
    open(img, "wb").write(image)
    r = fc.run(fc.OBJFILE, "encode", tag, img, path)
    if r.returncode:
        raise SystemExit("encode %s: %s%s" % (path, r.stdout, r.stderr))


class Fast:
    def __init__(self):
        import equip_service as es
        cur = es.served()[1]
        if cur:                                   # a Guardian made in the creator: patched in place
            self.out = cur[1]
            roster = os.path.join(cur[1], "roster")
            char, prof = os.path.join(cur[1], "char.bin"), os.path.join(cur[1], "profile.bin")
        else:
            self.out = os.path.join(es.LIVE, "fast")
            roster = os.path.join(self.out, "roster")
            shutil.rmtree(self.out, ignore_errors=True)
            shutil.copytree(os.path.join(fc.REPO, os.path.dirname(fc.FILES[0][1])), roster)
            char, prof = os.path.join(fc.REPO, fc.FILES[1][1]), os.path.join(fc.REPO, fc.FILES[2][1])
        self.peer_path = glob.glob(os.path.join(roster, "f0t1-*.bin"))[0]
        self.char = _decode(CHAR[0], char)
        self.peer = _decode(PEER[0], self.peer_path)
        self.prof = _decode(PROF[0], prof)
        self.items = {}                           # SOID -> (ordinal, {"char" / "peer": (entry, perks, stats)})
        self.learn(self.char, self.peer)

    def learn(self, char, peer, only=None):
        for o in range(20):
            soid = struct.unpack_from("<Q", char, CHAR[1] + o * 0x40)[0]
            if not soid or (only and soid != only) or soid in self.items:
                continue
            parts = {}
            for name, image, equip in (("char", char, CHAR[1]), ("peer", peer, PEER[1])):
                k = o - WEAPONS[0]
                e, p, s = equip + o * 0x40, equip + 0x5C0 + k * 0x20, equip + 0x6A0 + k * 0x80
                weapon = o in WEAPONS
                parts[name] = (bytes(image[e:e + 0x40]), bytes(image[p:p + 0x20]) if weapon else None,
                               bytes(image[s:s + 0x80]) if weapon else None)
            self.items[soid] = (o, parts)

    def warm(self):
        """Learn every spare item: one slow build each, into a scratch folder."""
        import equip_service as es
        el = es.elements()
        first = {}
        for n in sorted(el):
            first.setdefault(el[n][0], n)
        for n in sorted(el):
            soid = es.BASE_SOID + n
            if first[el[n][0]] == n or soid in self.items:
                continue
            try:
                scratch = es.build([soid], os.path.join(es.LIVE, "warm"))
                peer = glob.glob(os.path.join(scratch, "roster", "f0t1-*.bin"))[0]
                self.learn(_decode(CHAR[0], os.path.join(scratch, "char.bin")), _decode(PEER[0], peer), only=soid)
                print(time.strftime("%H:%M:%S"), "learned %#x (%s)" % (soid, el[n][0]), flush=True)
            except SystemExit as e:
                print("could not learn %#x: %s" % (soid, e), flush=True)

    def equip(self, soid):
        """Patch and encode; returns the D1_SWAP_TRIGGER lines, or None if the item is not known."""
        if soid not in self.items:
            return None
        o, parts = self.items[soid]
        for name, image, equip in (("char", self.char, CHAR[1]), ("peer", self.peer, PEER[1])):
            entry, perks, stats = parts[name]
            image[equip + o * 0x40:equip + o * 0x40 + 0x40] = entry
            if perks is not None:
                k = o - WEAPONS[0]
                image[equip + 0x5C0 + k * 0x20:equip + 0x5C0 + k * 0x20 + 0x20] = perks
                image[equip + 0x6A0 + k * 0x80:equip + 0x6A0 + k * 0x80 + 0x80] = stats
        struct.pack_into("<Q", self.prof, EQUIPPED_LIST + o * 8, soid)
        os.makedirs(self.out, exist_ok=True)
        char, prof = os.path.join(self.out, "char.bin"), os.path.join(self.out, "profile.bin")
        jobs = [threading.Thread(target=_encode, args=a) for a in
                ((CHAR[0], bytes(self.char), char), (PEER[0], bytes(self.peer), self.peer_path),
                 (PROF[0], bytes(self.prof), prof))]
        for j in jobs:
            j.start()
        for j in jobs:
            j.join()
        return ("D1_ROSTER_DIR=%s\nD1_CHARACTER_FILE=%s\nD1_PROFILE_FILE=%s\nFAMILIES=0,3,4\n"
                % (os.path.dirname(self.peer_path), char, prof))

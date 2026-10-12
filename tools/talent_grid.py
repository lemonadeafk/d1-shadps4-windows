r"""A subclass's abilities, read from its talent grid definition in the game files.

    python tools\talent_grid.py <grid index> [...]      130 Bladedancer, 131 Gunslinger,
        132 Striker, 133 Defender, 134 Sunsinger, 135 Voidwalker, 888 Nightstalker,
        889 Sunbreaker, 890 Stormcaller

The grid table (tag 0x80A5E227: 0x18-byte rows, definition tag @+0x10) names each grid's
definition. A definition has a node list (0x40 B per node: step count @+0x18, self-relative
step data @+0x20, exclusive-set hash @+0x38). A node's step data holds lists of
0x808018E8 {u32 option hash, u8 target ability row @+4, u8 ability row @+0xB, u32 slot @+0xC}
and 0x80804628 (u16 perk indices).

default_active(): one node per exclusive set (the first) plus every set-less node - a
consistent set (an inconsistent one crashes the grid screen, NIGHT-NOTES section 35); for the
Bladedancer it is exactly the set served since section 43.
abilities(): what tools\finish_character.py writes into the character: for each of the five
ability slots the ability-table row (first node naming the slot wins) and the option hashes
aimed at that row, plus the perk indices. NIGHT-NOTES sections 43 and 67.
"""
import os
import struct
import subprocess
import sys
import tempfile

REPO = r"C:\d1server\d1preservation"
ORACLE = os.path.join(REPO, r"d1-server\target\release\d1-oracle.exe")
GRID_TABLE = 0x80A5E227
UNSET = 0x811C9DC5
NO_PERK = 256


def _entry(tag):
    path = os.path.join(tempfile.gettempdir(), "d1_tag_%08x.bin" % tag)
    if not os.path.exists(path):
        r = subprocess.run([ORACLE, "oodle", "entry", "--tag", hex(tag), "-o", path], cwd=REPO,
                           capture_output=True, text=True)
        if not os.path.exists(path):
            raise SystemExit("could not extract tag %#x: %s" % (tag, r.stderr[-300:]))
    return open(path, "rb").read()


def definition(grid):
    t = _entry(GRID_TABLE)
    rows = 8 + 0x18 + struct.unpack_from("<Q", t, 8 + 8)[0]
    return _entry(struct.unpack_from("<I", t, rows + grid * 0x18 + 0x10)[0])


def nodes(g):
    q = lambda o: struct.unpack_from("<Q", g, o)[0]
    first = 0x18 + q(0x18) + 0x10
    return [dict(i=i, data=first + i * 0x40 + 0x20 + q(first + i * 0x40 + 0x20),
                 set=struct.unpack_from("<I", g, first + i * 0x40 + 0x38)[0]) for i in range(q(0x10))]


def default_active(grid):
    seen, out = set(), []
    for n in nodes(definition(grid)):
        if n["set"] == UNSET or n["set"] not in seen:
            seen.add(n["set"])
            out.append(n["i"])
    return out


def abilities(grid, active=None):
    g = definition(grid)
    ns = nodes(g)
    active = default_active(grid) if active is None else active
    starts = [n["data"] for n in ns]
    rows, options, perks = {}, [], []
    for n in ns:
        if n["i"] not in active:
            continue
        end = min([s for s in starts if s > n["data"]] + [len(g)])
        o = n["data"]
        while o + 16 <= end:
            count, tag = struct.unpack_from("<QI", g, o)
            if tag >> 16 == 0x8080 and count < 64:
                if tag == 0x808018E8:
                    for k in range(count):
                        h, a, b, slot = struct.unpack_from("<IIII", g, o + 16 + k * 16)
                        if (b >> 24) & 0xFF != 0xFF:
                            rows.setdefault(slot, (b >> 24) & 0xFF)
                        if h != UNSET:
                            options.append((h, a & 0xFF))
                elif tag == 0x80804628:
                    perks += [p for p in struct.unpack_from("<%dH" % count, g, o + 16) if p != NO_PERK]
            o += 4
    slots = []
    for slot in range(5):
        row = rows.get(slot, 0)
        slots.append((row, [h for h, target in options if target == row]))
    return {"slots": slots, "perks": perks}


if __name__ == "__main__":
    for grid in [int(a) for a in sys.argv[1:]]:
        a = abilities(grid)
        print(grid, "nodes", default_active(grid))
        print("   rows", [r for r, _ in a["slots"]], "options", [[hex(h) for h in o] for _, o in a["slots"]],
              "perks", a["perks"])

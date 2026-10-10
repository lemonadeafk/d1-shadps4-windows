"""Make the Director show a destination's activities (run while the Director is open).

    python tools\\director_fix.py            # Earth
    python tools\\director_fix.py tower      # the Tower book
    python tools\\director_fix.py 0x<hash>   # any destination-book hash

Why: cui::c_director_data_component_v2 +0x8C holds the destination hash the Director wants to show.
On our server it is 0x575b7710, which matches none of the 9 destination books, so the selected-book
index (+0x163) stays -1 and the panel (cui::c_director_panel_widget) builds 0 activity nodes. Writing
a real book hash and clearing the two "already built for this version" stamps (data +0x15C, panel
+0x298) makes the game rebuild the page with its own code. A memory poke, not a server fix.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d1guest_win import d1guest  # noqa: E402

BOOKS = {"earth": 0xA15E9435, "tower": 0x1C36C0EE}
DATA_V2_VTABLE = 0x19433A0    # cui::c_director_data_component_v2
PANEL_VTABLE = 0x1943680      # cui::c_director_panel_widget

ap = argparse.ArgumentParser()
ap.add_argument("book", nargs="?", default="earth")
a = ap.parse_args()
want = BOOKS.get(a.book.lower()) or int(a.book, 0)

ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
_, _, proc, guest = d1guest.open_guest(ns)
B = guest.base


def one(vt, what):
    hits, _ = proc.find(struct.pack("<Q", B + vt), limit=4)
    if len(hits) != 1:
        raise SystemExit(f"expected 1 {what}, found {len(hits)} - is the Director open?")
    return hits[0]


dv = one(DATA_V2_VTABLE, "director data component")
panel = one(PANEL_VTABLE, "director panel")
old = struct.unpack("<I", proc.read(dv + 0x8C, 4))[0]
proc.write(dv + 0x8C, struct.pack("<I", want))
proc.write(dv + 0x15C, struct.pack("<I", 0xFFFFFFFF))
proc.write(panel + 0x298, struct.pack("<I", 0xFFFFFFFE))
print(f"director destination {old:#010x} -> {want:#010x}; page rebuild requested")

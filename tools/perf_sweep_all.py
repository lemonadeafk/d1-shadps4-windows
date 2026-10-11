r"""Step every candidate performance through ALL performance sensors of one bubble, with a
screenshot per step, then build labelled contact sheets.

    python tools\perf_sweep_all.py <bubble> <out dir> [--hold 5] [--b HEX]
"""
import argparse, json, os, struct, sys, time, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import inject_sensor, gamewin
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("bubble", type=int); ap.add_argument("out"); ap.add_argument("--hold", type=float, default=5)
ap.add_argument("--b", default=None, help="second hash (hex); default = FNV basis")
ap.add_argument("--seq0", type=int, default=1000)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
cache = os.path.join(tempfile.gettempdir(), "d1-world-sensors", f"v1-80c7a005-{a.bubble}.txt")
slots = [l.split() for l in open(cache) if l.startswith("slot ")]
sens = [(s[1], int(s[3])) for s in slots if s[2] == "40"]
table = json.load(open(os.path.join(ROOT, "capture", "tower-plaza-performance-hashes.json")))
cands = [l for g in table.values() if not isinstance(g, str) for key, l in g if key == 0xafb11a12][0]
default = open(os.path.join(ROOT, "capture", "values", "default_kind40.bin"), "rb").read()
gamewin.shot_bg(os.path.join(a.out, "base.png"))
for n, h in enumerate(cands):
    v = bytearray(default); v[0:4] = struct.pack("<I", h); v[8:12] = struct.pack("<I", a.seq0 + n)
    if a.b:
        v[4:8] = struct.pack("<I", int(a.b, 16))
    ok = inject_sensor.inject(a.bubble, [f"0x{g}:{sub}:{v.hex()}" for g, sub in sens])
    time.sleep(a.hold)
    gamewin.shot_bg(os.path.join(a.out, f"{n:02d}.png"))
    print(f"{n:2d} {h:#010x} sent={ok}", flush=True)
names = ["base"] + [f"{n:02d}" for n in range(len(cands))]
W, H, COLS = 320, 180, 6
for page in range(0, len(names), 30):
    chunk = names[page:page + 30]
    sheet = Image.new("RGB", (W * COLS, H * ((len(chunk) + COLS - 1) // COLS)))
    for i, nm in enumerate(chunk):
        im = Image.open(os.path.join(a.out, nm + ".png")).convert("RGB").resize((W, H))
        ImageDraw.Draw(im).rectangle([0, 0, 46, 16], fill=(0, 0, 0)); ImageDraw.Draw(im).text((3, 2), nm, fill=(255, 255, 0))
        sheet.paste(im, ((i % COLS) * W, (i // COLS) * H))
    sheet.save(os.path.join(a.out, f"sheet{page // 30}.png"))
print("sheets written")

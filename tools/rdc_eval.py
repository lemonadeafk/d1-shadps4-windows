r"""Evaluate one pixel of a shadPS4 fragment shader outside the GPU.

    python tools\rdc_eval.py <capture.rdc> <work-dir> <eid> <x> <y> [name ...]

RenderDoc's shader debugger refuses these shaders (per-vertex barycentric inputs), so this runs
the RenderDoc SPIR-V disassembly (rdc_survey "shader" job) with the pass's real inputs:
storage buffers ("buffers" job), vertex outputs ("postvs"), and texel values ("pick", fetched on
demand and cached in <work-dir>\texels.json; nearest texel, no filtering). Prints the output
colour and any named intermediate values.

Constants in the disassembly are printed with 4 decimals, so results are approximate.
"""
import json
import math
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def rdc(cap, out, job):
    subprocess.run([sys.executable, os.path.join(HERE, "rdc_run.py"), cap, out, json.dumps(job)],
                   capture_output=True, timeout=900)


def f2u(f):
    return struct.unpack("<I", struct.pack("<f", f))[0]


def u2f(u):
    return struct.unpack("<f", struct.pack("<I", u & 0xFFFFFFFF))[0]


class Missing(Exception):
    pass


def main():
    cap, work, eid, px, py = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    names = sys.argv[6:]
    os.makedirs(work, exist_ok=True)
    sh = os.path.join(work, f"shader-{eid}.txt")
    if not os.path.exists(sh):
        rdc(cap, work, {"shader": [eid]})
    insp = os.path.join(work, f"inspect-{eid}.txt")
    if not os.path.exists(insp):
        rdc(cap, work, {"inspect": [eid]})
    pv = os.path.join(work, f"postvs-{eid}.txt")
    if not os.path.exists(pv):
        rdc(cap, work, {"postvs": [eid]})
    text = open(insp, encoding="utf-8").read().split("stage 5")[0]
    images = [(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
              for m in re.finditer(r"ro\[\d+\] res=(\d+) -> .*?-(\d+)x(\d+)x(\d+)a\d+\.png", text)]
    bufs = [(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            for m in re.finditer(r"rw\[\d+\] buffer res=(\d+) byteOffset=(\d+) byteSize=(\d+)", text)]
    bf = os.path.join(work, f"buffers-{eid}.txt")
    if not os.path.exists(bf):
        rdc(cap, work, {"buffers_eid": eid, "buffers": [list(b) for b in bufs]})
    ssbo = []
    for blk in open(bf).read().split("== buffer")[1:]:
        ssbo.append(bytes.fromhex("".join(l.split()[-1] for l in blk.strip().split("\n")[1:])))
    verts = [[float(v) for v in l.split(":")[1].split()] for l in open(pv) if re.match(r"v\d+:", l)][:3]
    # the pass draws one screen-space triangle; attributes are affine in the pixel position
    P = [((v[0] + 1) * 8192.0, (v[1] + 1) * 8192.0) for v in verts]
    e1 = (P[1][0] - P[0][0], P[1][1] - P[0][1])
    e2 = (P[2][0] - P[0][0], P[2][1] - P[0][1])
    dx, dy = px + 0.5 - P[0][0], py + 0.5 - P[0][1]
    det = e1[0] * e2[1] - e2[0] * e1[1]
    by = (dx * e2[1] - e2[0] * dy) / det
    bz = (e1[0] * dy - dx * e1[1]) / det
    bary = (1 - by - bz, by, bz)
    builtins = dict(re.findall(r"Input \S+ (_\d+) : \[\[BuiltIn\((\w+)\)\]\]", open(sh, encoding="utf-8").read()))

    cache_path = os.path.join(work, "texels.json")
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}

    def texel(img, coords, normalized):
        res, w, h, d = images[img]
        if normalized:
            x = min(w - 1, max(0, int(math.floor(coords[0] * w))))
            y = min(h - 1, max(0, int(math.floor(coords[1] * h))))
            z = min(d - 1, max(0, int(math.floor(coords[2] * d)))) if len(coords) > 2 else 0
        else:
            x, y, z = int(coords[0]), int(coords[1]), 0
        key = f"{res},{x},{y},{z}"
        if key not in cache:
            raise Missing(key)
        return cache[key]

    lines = [l.rstrip() for l in open(sh, encoding="utf-8")]
    start = next(i for i, l in enumerate(lines) if l.startswith("void_id"))
    body = lines[start + 1:]

    def run():
        env, ptr, out = {}, {}, {}
        active = [True]

        def val(tok):
            tok = tok.strip()
            if tok in env:
                return env[tok]
            if re.fullmatch(r"-?\d+\.\d+(e[+-]?\d+)?", tok):
                return float(tok)
            if re.fullmatch(r"-?\d+", tok):
                return int(tok)
            if tok.startswith("-") and tok[1:] in env:
                return -env[tok[1:]]
            if tok.startswith("!") and tok[1:] in env:
                return not env[tok[1:]]
            m = re.fullmatch(r"(\w+)\.([xyzw])", tok)
            if m and m.group(1) in env:
                return env[m.group(1)]["xyzw".index(m.group(2))]
            raise KeyError(tok)

        def args_of(s):
            depth, cur, res = 0, "", []
            for ch in s:
                if ch in "({":
                    depth += 1
                if ch in ")}":
                    depth -= 1
                if ch == "," and depth == 0:
                    res.append(cur)
                    cur = ""
                else:
                    cur += ch
            if cur.strip():
                res.append(cur)
            return [a.strip() for a in res]

        for raw in body:
            l = raw.strip()
            if not l or l == "return;":
                continue
            if l == "}":
                if len(active) > 1:
                    active.pop()
                continue
            m = re.fullmatch(r"if\((\w+)\) \{", l)
            if m:
                active.append(active[-1] and bool(env.get(m.group(1), False)))
                continue
            if not active[-1]:
                continue
            m = re.fullmatch(r"\*(\w+) = (.+);", l)
            if m:
                out[ptr[m.group(1)]] = val(m.group(2))
                continue
            m = re.fullmatch(r"([\w<>, ]+?\*?) (\w+) = (.+);", l)
            if not m:
                continue
            typ, name, rhs = m.group(1), m.group(2), m.group(3)
            if rhs.startswith("&"):
                ptr[name] = rhs[1:]
                continue
            if rhs.startswith("*"):
                tgt = ptr.get(rhs[1:], rhs[1:])
                if tgt.startswith("push_data"):
                    env[name] = 0
                elif re.fullmatch(r"_\d+(\.[xyzw])?", tgt) and tgt.split(".")[0] in builtins:
                    # a built-in input (which one is read from the module's decorations)
                    whole = ((px + 0.5, py + 0.5, 0.0, 1.0) if builtins[tgt.split(".")[0]] == "FragCoord"
                             else bary)
                    env[name] = whole["xyzw".index(tgt[-1])] if "." in tgt else whole
                elif tgt == "_49" or "BaryCoord" in tgt:
                    env[name] = bary
                elif tgt.startswith("ssbo_"):
                    mm = re.fullmatch(r"ssbo_(\d+)\.data\[(\w+)\]", tgt)
                    data = ssbo[int(mm.group(1)) - 1]
                    env[name] = struct.unpack_from("<I", data, 4 * val(mm.group(2)))[0]
                elif tgt.startswith("fs_in_attr"):
                    mm = re.fullmatch(r"fs_in_attr(\d+)_p\[(\d)\]\.([xyzw])", tgt)
                    a, vtx, c = int(mm.group(1)), int(mm.group(2)), "xyzw".index(mm.group(3))
                    env[name] = verts[vtx][4 + 4 * a + c]
                elif tgt.startswith("fs_img") or tgt.startswith("fs_samp"):
                    env[name] = tgt
                else:
                    env[name] = tgt
                continue
            m2 = re.fullmatch(r"([\w.:]+)\((.*)\)", rhs)
            if m2 and m2.group(1) not in ("u32_id", "f32vec4_id", "f32vec3_id", "f32vec2_id"):
                fn, a = m2.group(1).split("::")[-1], args_of(m2.group(2))
                if fn == "Bitcast":
                    v = val(a[0])
                    one = lambda q: (q if isinstance(q, float) else u2f(q)) if typ.startswith("f32") else (f2u(q) if isinstance(q, float) else q)
                    env[name] = [one(q) for q in v] if isinstance(v, list) else one(v)
                elif fn == "BitFieldUExtract":
                    env[name] = (val(a[0]) >> val(a[1])) & ((1 << val(a[2])) - 1)
                elif fn == "Fma":
                    env[name] = val(a[0]) * val(a[1]) + val(a[2])
                elif fn == "FClamp":
                    env[name] = min(max(val(a[0]), val(a[1])), val(a[2]))
                elif fn == "FMin":
                    env[name] = min(val(a[0]), val(a[1]))
                elif fn == "FMax":
                    env[name] = max(val(a[0]), val(a[1]))
                elif fn == "Sqrt":
                    env[name] = math.sqrt(max(val(a[0]), 0.0))
                elif fn == "InverseSqrt":
                    v = val(a[0])
                    env[name] = 1.0 / math.sqrt(v) if v > 0 else float("inf")
                elif fn == "Exp2":
                    env[name] = 2.0 ** min(val(a[0]), 120.0)
                elif fn == "Log2":
                    v = val(a[0])
                    env[name] = math.log2(v) if v > 0 else float("-inf")
                elif fn == "Fract":
                    env[name] = val(a[0]) - math.floor(val(a[0]))
                elif fn in ("Sin", "Cos", "Exp", "Ceil", "Trunc"):
                    env[name] = float(getattr(math, fn.lower())(val(a[0])))
                elif fn == "Round" or fn == "RoundEven":
                    env[name] = float(round(val(a[0])))
                elif fn == "Log":
                    v = val(a[0])
                    env[name] = math.log(v) if v > 0 else float("-inf")
                elif fn == "Pow":
                    env[name] = max(val(a[0]), 0.0) ** val(a[1])
                elif fn == "FSign":
                    v = val(a[0])
                    env[name] = float((v > 0) - (v < 0))
                elif fn in ("FMix", "Mix"):
                    env[name] = val(a[0]) * (1 - val(a[2])) + val(a[1]) * val(a[2])
                elif fn in ("NMin", "SMin", "UMin"):
                    env[name] = min(val(a[0]), val(a[1]))
                elif fn in ("NMax", "SMax", "UMax"):
                    env[name] = max(val(a[0]), val(a[1]))
                elif fn in ("NClamp", "SClamp", "UClamp"):
                    env[name] = min(max(val(a[0]), val(a[1])), val(a[2]))
                elif fn in ("ConvertSToF", "ConvertUToF"):
                    v = val(a[0])
                    if fn == "ConvertSToF" and v >= 1 << 31:
                        v -= 1 << 32
                    env[name] = float(v)
                elif fn == "ConvertFToU":
                    env[name] = max(int(val(a[0])), 0)
                elif fn in ("Not", "LogicalNot"):
                    v = val(a[0])
                    env[name] = (not v) if isinstance(v, bool) else (~v & 0xFFFFFFFF)
                elif fn == "FNegate":
                    env[name] = -val(a[0])
                elif fn == "IsNan":
                    env[name] = val(a[0]) != val(a[0])
                elif fn == "IsInf":
                    env[name] = abs(val(a[0])) == float("inf")
                elif fn == "BitFieldSExtract":
                    v = (val(a[0]) >> val(a[1])) & ((1 << val(a[2])) - 1)
                    env[name] = v - (1 << val(a[2])) if v >> (val(a[2]) - 1) else v
                elif fn == "Floor":
                    env[name] = float(math.floor(val(a[0])))
                elif fn == "FAbs":
                    env[name] = abs(val(a[0]))
                elif fn == "ConvertFToS":
                    env[name] = int(val(a[0]))
                elif fn == "Select":
                    env[name] = val(a[1]) if val(a[0]) else val(a[2])
                elif fn == "Phi":
                    env[name] = env[a[0]] if a[0] in env else (env[a[1]] if a[1] in env else 0)
                elif fn == "CompositeConstruct":
                    env[name] = [val(x) for x in args_of(a[0].strip()[1:-1])]
                elif fn == "SampledImage":
                    env[name] = env[a[0]]
                elif fn in ("ImageFetch", "ImageSampleImplicitLod", "ImageSampleExplicitLod"):
                    img = int(re.search(r"fs_img(\d+)", str(env[a[0]])).group(1))
                    env[name] = texel(img, val(a[1]), fn != "ImageFetch")
                else:
                    raise SystemExit(f"unsupported op {fn}: {l}")
                continue
            m2 = re.fullmatch(r"(\S+) (\+|-|\*|/|>|<|>=|<=|==|!=|\|\||&&|>>|<<|&|\|) (\S+)", rhs)
            if m2:
                x, op, y = val(m2.group(1)), m2.group(2), val(m2.group(3))
                if isinstance(x, (list, str)) or isinstance(y, (list, str)):
                    raise SystemExit(f"non-scalar operand: {l}  x={x!r} y={y!r}")
                if op == "/":
                    env[name] = x / y if y else float("inf")
                else:
                    env[name] = {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y,
                                 ">": lambda: x > y, "<": lambda: x < y, ">=": lambda: x >= y,
                                 "<=": lambda: x <= y, "==": lambda: x == y, "!=": lambda: x != y,
                                 "||": lambda: bool(x) or bool(y), "&&": lambda: bool(x) and bool(y),
                                 ">>": lambda: x >> y, "<<": lambda: x << y, "&": lambda: x & y,
                                 "|": lambda: x | y}[op]()
                continue
            env[name] = val(rhs)
        return env, out

    for _ in range(40):
        try:
            env, out = run()
            break
        except Missing as e:
            res, x, y, z = (int(v) for v in str(e).split(","))
            rdc(cap, work, {"pick": [[eid, res, x, y, z]]})
            line = open(os.path.join(work, "pick-values.txt")).read().strip()
            cache[str(e)] = [float(v) for v in line.split("=")[1].split()]
            json.dump(cache, open(cache_path, "w"))
    print("pixel", px, py, "bary", [round(b, 4) for b in bary])
    for k in sorted(out):
        print("OUT", k, out[k])
    for n in names:
        print(n, "=", env.get(n, "<undefined>"))
    json.dump({k: (v if isinstance(v, (int, float, bool, list, str)) else str(v)) for k, v in env.items()},
              open(os.path.join(work, f"env-{px}-{py}.json"), "w"))


if __name__ == "__main__":
    main()

"""RenderDoc survey of one shadPS4 frame: run INSIDE qrenderdoc, which embeds Python + renderdoc.

    qrenderdoc.exe --python tools\\rdc_survey.py
    (paths come from the environment: RDC_IN = capture, RDC_OUT = output folder)

Writes RDC_OUT/actions.tsv (every action: eid, kind, size, outputs, marker path) and
RDC_OUT/textures.tsv, then saves each large colour target as it stands after the LAST action that
wrote it (tex-<eid>-<id>-<fmt>-<w>x<h>.png). Exits the process when done.
"""

import json
import os
import sys
import traceback

# qrenderdoc may not pass our environment through, so the paths also come from rdc_survey.json
# next to this script ({"in": ..., "out": ..., "min_w": ...}). A marker proves the script ran.
_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(os.path.expanduser("~"), "Desktop", "shadgames", "tools")
with open(os.path.join(os.environ.get("TEMP", "."), "rdc_survey.started"), "w") as _m:
    _m.write(sys.version)
try:
    _cfg = json.load(open(os.path.join(_HERE, "rdc_survey.json")))
except OSError:
    _cfg = {}
IN = _cfg.get("in") or os.environ["RDC_IN"]
OUT = _cfg.get("out") or os.environ["RDC_OUT"]
MIN_W = int(_cfg.get("min_w") or os.environ.get("RDC_MIN_W", "640"))
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "survey.log"), "w", encoding="utf-8")

import renderdoc as rd  # noqa: E402


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


def kind(flags):
    for name, bit in (("draw", rd.ActionFlags.Drawcall), ("dispatch", rd.ActionFlags.Dispatch),
                      ("clear", rd.ActionFlags.Clear), ("copy", rd.ActionFlags.Copy),
                      ("resolve", rd.ActionFlags.Resolve), ("present", rd.ActionFlags.Present),
                      ("pass", rd.ActionFlags.PassBoundary), ("marker", rd.ActionFlags.PushMarker)):
        if flags & bit:
            return name
    return "other"


def main():
    cap = rd.OpenCaptureFile()
    status = cap.OpenFile(IN, "", None)
    if status != rd.ResultCode.Succeeded:
        log("OpenFile failed", status)
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        log("OpenCapture failed", status)
        return

    textures = {t.resourceId: t for t in ctl.GetTextures()}
    with open(os.path.join(OUT, "textures.tsv"), "w", encoding="utf-8") as f:
        f.write("id\tformat\tw\th\tdepth\tarray\tmips\ttype\tname\n")
        for t in textures.values():
            name = ""
            try:
                name = ctl.GetResourceName(t.resourceId) if hasattr(ctl, "GetResourceName") else ""
            except Exception:
                pass
            f.write(f"{int(t.resourceId)}\t{t.format.Name()}\t{t.width}\t{t.height}\t{t.depth}\t"
                    f"{t.arraysize}\t{t.mips}\t{t.type}\t{name}\n")

    last_writer = {}      # texture id -> eid of the last action that bound it as a colour output
    rows = []

    def walk(actions, path):
        for a in actions:
            label = a.GetName(ctl.GetStructuredFile())
            if a.children:
                walk(a.children, path + [label])
                continue
            outs = [o for o in a.outputs if o != rd.ResourceId.Null()]
            for o in outs:
                last_writer[o] = a.eventId
            rows.append((a.eventId, kind(a.flags), a.numIndices, a.dispatchDimension,
                         [int(o) for o in outs], int(a.depthOut) if a.depthOut != rd.ResourceId.Null() else 0,
                         " / ".join(path[-3:]) + " :: " + label))
    walk(ctl.GetRootActions(), [])

    with open(os.path.join(OUT, "actions.tsv"), "w", encoding="utf-8") as f:
        f.write("eid\tkind\tindices\tdispatch\toutputs\tdepth\tpath\n")
        for eid, k, ni, dd, outs, dep, p in rows:
            f.write(f"{eid}\t{k}\t{ni}\t{tuple(dd)}\t{outs}\t{dep}\t{p}\n")
    log("actions", len(rows), "textures", len(textures), "written targets", len(last_writer))

    saved = 0
    for tid, eid in sorted(last_writer.items(), key=lambda kv: kv[1]):
        t = textures.get(tid)
        if t is None or t.width < MIN_W:
            continue
        ctl.SetFrameEvent(eid, True)
        ts = rd.TextureSave()
        ts.resourceId = tid
        ts.destType = rd.FileType.PNG
        ts.mip = 0
        ts.slice.sliceIndex = 0
        ts.alpha = rd.AlphaMapping.Discard
        fn = os.path.join(OUT, f"tex-{eid:06d}-{int(tid)}-{t.format.Name()}-{t.width}x{t.height}.png")
        ok = ctl.SaveTexture(ts, fn)
        log("save", fn, ok)
        saved += 1
    log("saved", saved)
    ctl.Shutdown()
    cap.Shutdown()


def inspect(eids):
    """For each eid: save its colour outputs AFTER the action, and every texture its pixel /
    compute shader reads, with the bindings written to inspect-<eid>.txt."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        log("OpenFile failed")
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        log("OpenCapture failed", status)
        return
    textures = {t.resourceId: t for t in ctl.GetTextures()}

    def save(tid, eid, tag, sl=0):
        t = textures.get(tid)
        if t is None:
            return "not a texture"
        ts = rd.TextureSave()
        ts.resourceId = tid
        ts.destType = rd.FileType.PNG
        ts.mip = 0
        ts.slice.sliceIndex = sl
        ts.alpha = rd.AlphaMapping.Discard
        fn = os.path.join(OUT, f"insp-{eid:06d}-{tag}-{int(tid)}-{t.format.Name()}-{t.width}x{t.height}x{t.depth}a{t.arraysize}.png")
        return f"{ctl.SaveTexture(ts, fn)} {os.path.basename(fn)}"

    for eid in eids:
        lines = []
        ctl.SetFrameEvent(eid, True)
        st = ctl.GetPipelineState()
        for stage in (rd.ShaderStage.Pixel, rd.ShaderStage.Compute):
            refl = st.GetShaderReflection(stage)
            if refl is None:
                continue
            lines.append(f"stage {stage} shader {st.GetShader(stage)} entry {st.GetShaderEntryPoint(stage)}")
            lines.append(f"  reflection: {len(refl.readOnlyResources)} ro, {len(refl.readWriteResources)} rw, "
                         f"{len(refl.constantBlocks)} cbuffers, {len(refl.samplers)} samplers: "
                         + ", ".join(r.name for r in refl.readOnlyResources))
            ro = []
            for only_used in (True, False):
                try:
                    ro = st.GetReadOnlyResources(stage, only_used)
                except Exception as e:  # noqa: BLE001
                    lines.append(f"  GetReadOnlyResources({only_used}) failed: {e!r}")
                    continue
                lines.append(f"  GetReadOnlyResources(onlyUsed={only_used}) -> {len(ro)} entries; "
                             f"first: {[dir(x) for x in ro[:1]]}")
                if ro:
                    break
            for i, used in enumerate(ro):
                rid = getattr(getattr(used, "descriptor", used), "resource", None)
                if rid is None or rid == rd.ResourceId.Null():
                    continue
                lines.append(f"  ro[{i}] res={int(rid)} -> {save(rid, eid, f'in{i}')}")
            try:
                rw = st.GetReadWriteResources(stage, True)
            except Exception as e:  # noqa: BLE001
                lines.append(f"  GetReadWriteResources failed: {e!r}")
                rw = []
            for i, used in enumerate(rw):
                desc = getattr(used, "descriptor", used)
                rid = getattr(desc, "resource", None)
                if rid is None or rid == rd.ResourceId.Null():
                    continue
                extra = f"byteOffset={getattr(desc, 'byteOffset', '?')} byteSize={getattr(desc, 'byteSize', '?')}"
                kind_ = "texture" if rid in textures else "buffer"
                saved = save(rid, eid, f"rw{i}") if kind_ == "texture" else "-"
                lines.append(f"  rw[{i}] {kind_} res={int(rid)} {extra} -> {saved}")
            for i, cb in enumerate(refl.constantBlocks):
                lines.append(f"  cbuffer[{i}] {cb.name} {cb.byteSize}B vars={len(cb.variables)}")
        for i, o in enumerate(st.GetOutputTargets()):
            rid = getattr(o, "resource", None) or getattr(getattr(o, "descriptor", None), "resource", None)
            if rid and rid != rd.ResourceId.Null():
                lines.append(f"  out[{i}] res={int(rid)} -> {save(rid, eid, f'out{i}')}")
        with open(os.path.join(OUT, f"inspect-{eid}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        log("inspected", eid, len(lines))
    ctl.Shutdown()
    cap.Shutdown()


def usage(ids):
    """Every event that touches each resource id, with the usage kind (read/write/target...)."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        return
    by_id = {int(t.resourceId): t.resourceId for t in ctl.GetTextures()}
    with open(os.path.join(OUT, "usage.txt"), "w", encoding="utf-8") as f:
        for i in ids:
            rid = by_id.get(i)
            if rid is None:
                f.write(f"{i}: not a texture\n")
                continue
            uses = ctl.GetUsage(rid)
            f.write(f"== {i}: {len(uses)} uses\n")
            for u in uses:
                f.write(f"  {u.eventId}\t{u.usage}\n")
    ctl.Shutdown()
    cap.Shutdown()


def buffers(eid, specs):
    """Dump [res_id, offset, size] buffer ranges as float32 at an event."""
    import struct
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        return
    ctl.SetFrameEvent(eid, True)
    by_id = {int(b.resourceId): b.resourceId for b in ctl.GetBuffers()}
    with open(os.path.join(OUT, f"buffers-{eid}.txt"), "w", encoding="utf-8") as f:
        for rid, off, size in specs:
            data = bytes(ctl.GetBufferData(by_id[rid], off, size))
            f.write(f"== buffer {rid} +{off} ({size}B)\n")
            for i in range(0, len(data) - len(data) % 16, 16):
                fl = struct.unpack_from("<4f", data, i)
                f.write(f"  +{i:4d}  " + "  ".join(f"{v:12.5g}" for v in fl) + f"   {data[i:i+16].hex()}\n")
    ctl.Shutdown()
    cap.Shutdown()


def pick(specs):
    """specs: [[eid, texture_id, x, y], ...] -> pick-values.txt with the float RGBA at each point."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        return
    by_id = {int(t.resourceId): t.resourceId for t in ctl.GetTextures()}
    with open(os.path.join(OUT, "pick-values.txt"), "w", encoding="utf-8") as f:
        last = None
        for spec in specs:
            eid, tid, x, y = spec[:4]
            sl = spec[4] if len(spec) > 4 else 0     # array layer / 3D depth slice
            if eid != last:
                ctl.SetFrameEvent(eid, True)
                last = eid
            v = ctl.PickPixel(by_id[tid], x, y, rd.Subresource(0, sl, 0), rd.CompType.Typeless)
            vals = "  ".join(f"{c:.6g}" for c in v.floatValue[:4])
            f.write(f"eid {eid} tex {tid} ({x},{y}) slice {sl} = {vals}" + chr(10))
    ctl.Shutdown()
    cap.Shutdown()


def history(specs):
    """specs: [[texture_id, x, y], ...] -> history-<tex>-<x>-<y>.txt: every event that touched the pixel."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        log("OpenCapture failed", status)
        return
    by_id = {int(t.resourceId): t.resourceId for t in ctl.GetTextures()}
    last_eid = max(a.eventId for a in ctl.GetRootActions()) if ctl.GetRootActions() else 0
    for tid, x, y in specs:
        ctl.SetFrameEvent(1 << 30, True)
        mods = ctl.PixelHistory(by_id[tid], x, y, rd.Subresource(0, 0, 0), rd.CompType.Typeless)
        with open(os.path.join(OUT, f"history-{tid}-{x}-{y}.txt"), "w", encoding="utf-8") as f:
            for m in mods:
                pre = m.preMod.col.floatValue[:4]
                post = m.postMod.col.floatValue[:4]
                sh = m.shaderOut.col.floatValue[:4]
                flags = []
                for name in ("sampleMasked", "backfaceCulled", "depthClipped", "viewClipped", "scissorClipped",
                             "shaderDiscarded", "depthTestFailed", "stencilTestFailed"):
                    if getattr(m, name, False):
                        flags.append(name)
                f.write(f"eid {m.eventId} prim {m.primitiveID} passed={m.Passed()} "
                        f"pre {[round(v, 5) for v in pre]} shader {[round(v, 5) for v in sh]} "
                        f"post {[round(v, 5) for v in post]} {' '.join(flags)}" + chr(10))
        log("history", tid, x, y, len(mods))
    ctl.Shutdown()
    cap.Shutdown()


def bufwatch(spec):
    """spec: {"rid":213,"off":N,"size":64,"eids":[...]} -> bufwatch.txt: the range as floats at each eid."""
    import struct
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        log("OpenCapture failed", status)
        return
    by_id = {int(b.resourceId): b.resourceId for b in ctl.GetBuffers()}
    with open(os.path.join(OUT, "bufwatch.txt"), "w", encoding="utf-8") as f:
        for eid in spec["eids"]:
            ctl.SetFrameEvent(eid, True)
            data = bytes(ctl.GetBufferData(by_id[spec["rid"]], spec["off"], spec["size"]))
            vals = struct.unpack("<%df" % (len(data) // 4), data)
            f.write(f"eid {eid}: " + " ".join(f"{v:.5g}" for v in vals) + chr(10))
    ctl.Shutdown()
    cap.Shutdown()


def apievents(spec):
    """spec: [first_eid, last_eid] -> apievents.txt: every API call in the range, with arguments."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        log("OpenCapture failed", status)
        return
    sf = ctl.GetStructuredFile()
    lo, hi = spec

    def dump(obj, depth, out):
        name = obj.name
        if obj.NumChildren() == 0:
            val = ""
            try:
                val = obj.AsString()
            except Exception:  # noqa: BLE001
                pass
            if val == "":
                for getter in ("AsInt", "AsUInt", "AsFloat", "AsResourceId"):
                    try:
                        val = getattr(obj, getter)()
                        break
                    except Exception:  # noqa: BLE001
                        continue
            out.append("  " * depth + f"{name} = {val}")
            return
        out.append("  " * depth + f"{name}:")
        if depth < 6:
            for i in range(obj.NumChildren()):
                dump(obj.GetChild(i), depth + 1, out)

    lines = []

    def walk(actions):
        for a in actions:
            for ev in a.events:
                if lo <= ev.eventId <= hi:
                    ch = sf.chunks[ev.chunkIndex]
                    lines.append(f"== eid {ev.eventId} {ch.name}")
                    if any(k in ch.name for k in ("Barrier", "Rendering", "Clear", "Copy", "Blit")):
                        out = []
                        for i in range(ch.NumChildren()):
                            dump(ch.GetChild(i), 1, out)
                        lines.extend(out[:120])
            walk(a.children)
    walk(ctl.GetRootActions())
    with open(os.path.join(OUT, "apievents.txt"), "w", encoding="utf-8") as f:
        f.write(chr(10).join(lines) + chr(10))
    ctl.Shutdown()
    cap.Shutdown()


def shader(eids):
    """For each eid: pixel-shader disassembly + colour blend / depth / stencil state -> shader-<eid>.txt."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        log("OpenCapture failed", status)
        return
    for eid in eids:
        ctl.SetFrameEvent(eid, True)
        st = ctl.GetPipelineState()
        out = []
        try:
            for i, b in enumerate(st.GetColorBlends()):
                out.append(f"blend[{i}] enabled={b.enabled} writeMask={b.writeMask} "
                           f"color=({b.colorBlend.source},{b.colorBlend.destination},{b.colorBlend.operation}) "
                           f"alpha=({b.alphaBlend.source},{b.alphaBlend.destination},{b.alphaBlend.operation})")
        except Exception as e:  # noqa: BLE001
            out.append(f"blend: {e!r}")
        try:
            vk = ctl.GetVulkanPipelineState()
            ds = vk.depthStencil
            out.append(f"depth test={ds.depthTestEnable} write={ds.depthWriteEnable} func={ds.depthFunction} "
                       f"stencil={ds.stencilTestEnable} front={ds.frontFace.function},{ds.frontFace.passOperation},"
                       f"{ds.frontFace.failOperation},{ds.frontFace.depthFailOperation} ref={ds.frontFace.reference}")
            out.append(f"raster cull={vk.rasterizer.cullMode} front={vk.rasterizer.frontCCW}")
        except Exception as e:  # noqa: BLE001
            out.append(f"vk state: {e!r}")
        refl = st.GetShaderReflection(rd.ShaderStage.Vertex if _cfg.get("stage") == "vs" else rd.ShaderStage.Pixel)
        try:
            stg = rd.ShaderStage.Vertex if _cfg.get("stage") == "vs" else rd.ShaderStage.Pixel
            for i, r in enumerate(st.GetReadOnlyResources(stg, False)):
                out.append(f"ro[{i}] {[str(x.descriptor.resource) for x in [r]]} {r!r}"[:300])
        except Exception as e:  # noqa: BLE001
            out.append(f"ro: {e!r}")
        if refl is not None:
            targets = ctl.GetDisassemblyTargets(True)
            pipe = st.GetGraphicsPipelineObject()
            out.append(f"targets {list(targets)}")
            out.append(ctl.DisassembleShader(pipe, refl, targets[0]))
        with open(os.path.join(OUT, f"shader-{eid}{'-vs' if _cfg.get('stage') == 'vs' else ''}.txt"), "w", encoding="utf-8") as f:
            f.write(chr(10).join(str(x) for x in out) + chr(10))
    ctl.Shutdown()
    cap.Shutdown()


def debugpixel(spec):
    """spec: {"eid":E,"x":X,"y":Y,"names":["_366",...]} -> debugpixel.txt: last value of each variable."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        log("OpenCapture failed", status)
        return
    ctl.SetFrameEvent(spec["eid"], True)
    inputs = rd.DebugPixelInputs()
    inputs.sample = 0
    inputs.primitive = rd.ReplayController.NoPreference
    trace = ctl.DebugPixel(spec["x"], spec["y"], inputs)
    out = [f"trace valid={trace.debugger is not None}"]
    want = set(spec.get("names", []))
    last = {}
    if trace.debugger is not None:
        steps = 0
        while True:
            states = ctl.ContinueDebug(trace.debugger)
            if not states:
                break
            for stt in states:
                steps += 1
                for ch in stt.changes:
                    v = ch.after
                    if not want or v.name in want:
                        try:
                            last[v.name] = list(v.value.f32v[:max(1, v.columns)])
                        except Exception:  # noqa: BLE001
                            last[v.name] = "?"
        out.append(f"steps {steps}")
        ctl.FreeDebugger(trace.debugger)
    for k in sorted(last):
        out.append(f"{k} = {last[k]}")
    with open(os.path.join(OUT, "debugpixel.txt"), "w", encoding="utf-8") as f:
        f.write(chr(10).join(out) + chr(10))
    ctl.Shutdown()
    cap.Shutdown()


def postvs(eids):
    """For each eid: the vertex-shader outputs (all vertices, as floats) -> postvs-<eid>.txt."""
    import struct as _st
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        return
    for eid in eids:
        ctl.SetFrameEvent(eid, True)
        out = []
        act = ctl.GetAction(eid) if hasattr(ctl, "GetAction") else None
        m = ctl.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
        out.append(f"numIndices={m.numIndices} stride={m.vertexByteStride} idx={m.indexResourceId} "
                   f"idxw={m.indexByteStride}")
        raw = ctl.GetBufferData(m.vertexResourceId, m.vertexByteOffset, 0)
        n = len(raw) // max(1, m.vertexByteStride)
        for i in range(min(n, 64)):
            row = raw[i * m.vertexByteStride:(i + 1) * m.vertexByteStride]
            out.append(f"v{i}: " + " ".join("%.6g" % v for v in _st.unpack("<%df" % (len(row) // 4), row)))
        if m.indexResourceId != rd.ResourceId.Null() and m.indexByteStride:
            ib = ctl.GetBufferData(m.indexResourceId, m.indexByteOffset, 0)
            fmt = {2: "H", 4: "I", 1: "B"}[m.indexByteStride]
            idx = _st.unpack("<%d%s" % (len(ib) // m.indexByteStride, fmt), ib)
            out.append("indices " + " ".join(str(x) for x in idx[:96]))
        with open(os.path.join(OUT, f"postvs-{eid}.txt"), "w", encoding="utf-8") as f:
            f.write(chr(10).join(out) + chr(10))
    ctl.Shutdown()
    cap.Shutdown()


def raster(eids):
    """Rasterizer depth-bias / depth-clamp / viewport depth range per eid -> raster.txt."""
    cap = rd.OpenCaptureFile()
    if cap.OpenFile(IN, "", None) != rd.ResultCode.Succeeded:
        return
    status, ctl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        return
    out = []
    for eid in eids:
        ctl.SetFrameEvent(eid, True)
        vk = ctl.GetVulkanPipelineState()
        r = vk.rasterizer
        vp = vk.viewportScissor.viewportScissors[0].vp if vk.viewportScissor.viewportScissors else None
        ds = vk.depthStencil
        out.append(f"{eid}: biasEnable={r.depthBiasEnable} constant={r.depthBias} clamp={r.depthBiasClamp} "
                   f"slope={r.slopeScaledDepthBias} depthClamp={r.depthClampEnable} "
                   f"vp=({vp.x},{vp.y},{vp.width},{vp.height},{vp.minDepth},{vp.maxDepth}) "
                   f"dtest={ds.depthTestEnable} dwrite={ds.depthWriteEnable} func={ds.depthFunction}")
        try:
            out.append(f"{eid}: pushconsts=" + bytes(vk.pushconsts).hex())
        except Exception as e:  # noqa: BLE001
            out.append(f"{eid}: pushconsts {e!r}")
    with open(os.path.join(OUT, "raster.txt"), "w", encoding="utf-8") as f:
        f.write(chr(10).join(out) + chr(10))
    ctl.Shutdown()
    cap.Shutdown()


try:
    if _cfg.get("raster"):
        raster(_cfg["raster"])
    elif _cfg.get("postvs"):
        postvs(_cfg["postvs"])
    elif _cfg.get("debugpixel"):
        debugpixel(_cfg["debugpixel"])
    elif _cfg.get("shader"):
        shader(_cfg["shader"])
    elif _cfg.get("apievents"):
        apievents(_cfg["apievents"])
    elif _cfg.get("bufwatch"):
        bufwatch(_cfg["bufwatch"])
    elif _cfg.get("history"):
        history(_cfg["history"])
    elif _cfg.get("pick"):
        pick(_cfg["pick"])
    elif _cfg.get("buffers"):
        buffers(_cfg["buffers_eid"], _cfg["buffers"])
    elif _cfg.get("usage"):
        usage(_cfg["usage"])
    elif _cfg.get("inspect"):
        inspect(_cfg["inspect"])
    else:
        main()
except Exception:
    log(traceback.format_exc())
finally:
    LOG.close()
    os._exit(0)

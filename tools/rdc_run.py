r"""Run tools\rdc_survey.py inside qrenderdoc with a given job, and wait for it (with a timeout).

    python tools\rdc_run.py <capture.rdc> <out-folder> [job-json]

    job-json examples:   {"inspect":[13876]}      {"usage":[7311]}
                         {"pick":[[13868,7311,150,850]]}
                         {"buffers_eid":12628,"buffers":[[213,46203712,16]]}
    no job = the full survey (actions.tsv + every large colour target).

Writes tools\rdc_survey.json (the only way to pass arguments: qrenderdoc does not forward argv or
the environment reliably) and kills qrenderdoc if it has not exited after 8 minutes - a script
error leaves its window open forever otherwise.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QRD = r"C:\d1server\renderdoc\RenderDoc_1.43_64\qrenderdoc.exe"

cfg = {"in": os.path.abspath(sys.argv[1]), "out": os.path.abspath(sys.argv[2]), "min_w": 640}
if len(sys.argv) > 3:
    cfg.update(json.loads(sys.argv[3]))
json.dump(cfg, open(os.path.join(HERE, "rdc_survey.json"), "w"), indent=1)
try:
    subprocess.run([QRD, "--python", os.path.join(HERE, "rdc_survey.py")], timeout=480)
except subprocess.TimeoutExpired:
    subprocess.run(["taskkill", "/F", "/IM", "qrenderdoc.exe"], capture_output=True)
    raise SystemExit("qrenderdoc did not exit in 8 minutes (script error?) - killed")
log = os.path.join(cfg["out"], "survey.log")
if os.path.exists(log):
    print(open(log, encoding="utf-8", errors="replace").read()[-600:])

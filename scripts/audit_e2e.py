"""Isolated audit-only real HTTP smoke test against Docker Compose (Redis/API/Celery)."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = "http://127.0.0.1:8000"
OP = {"Authorization": "Bearer " + os.environ["MAPS4U_OPERATOR_TOKEN"]}
REV = {"Authorization": "Bearer " + os.environ["MAPS4U_REVIEWER_TOKEN"]}
GEOFENCE = {"type": "Polygon", "coordinates": [[[153.085,-26.660],[153.105,-26.660],[153.105,-26.645],[153.085,-26.645],[153.085,-26.660]]]}

def req(method, path, data=None, headers=None, expect=200, binary=False):
    b = None if data is None else json.dumps(data).encode()
    h = dict(headers or {})
    if b is not None:
        h["Content-Type"] = "application/json"
    request = urllib.request.Request(ROOT + path, data=b, headers=h, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            code = response.status
            raw = response.read()
    except urllib.error.HTTPError as err:
        code = err.code
        raw = err.read()
    assert code == expect, f"{method} {path}: expected {expect}, got {code}: {raw[:500]!r}"
    if binary:
        return raw
    return json.loads(raw) if raw else None

def wait_ready():
    for _ in range(90):
        try:
            r = req("GET", "/readyz")
            if r["ready"] and r["worker"] and r["broker"]:
                print("PASS: DB, Redis and worker readiness", flush=True)
                return
        except Exception:
            pass
        time.sleep(2)
    raise AssertionError("Production API/worker readiness timed out")

def await_state(jid, goal="proof_ready"):
    for _ in range(150):
        job = req("GET", f"/api/jobs/{jid}", headers=OP)
        if job["status"] == goal:
            return job
        if job["status"] in ("failed", "rejected"):
            raise AssertionError(f"Unexpected job terminal state {job}")
        time.sleep(2)
    raise AssertionError(f"Job {jid} timed out before {goal}")

wait_ready()
req("GET", "/healthz")
req("GET", "/api/meta")
req("GET", "/api/projects", expect=401)
req("GET", "/api/projects", headers={"Authorization": "Bearer incorrect"}, expect=401)
req("POST", "/api/projects", {"area_name": "Forbidden reviewer"}, headers=REV, expect=403)
print("PASS: health, metadata, RBAC and missing/invalid credentials", flush=True)
project = req("POST", "/api/projects", {"area_name": "Maroochydore audit", "reference":"AUDIT-2026"}, headers=OP, expect=201)
pid = project["project_id"]
geofence = req("POST", f"/api/projects/{pid}/geofence", GEOFENCE, headers=OP, expect=201)
rid = geofence["revision_id"]
job = req("POST", "/api/jobs", {"project_id":pid,"geofence_revision":rid,"paper":"A4","orientation":"landscape","edition":"audit-01"},headers=OP,expect=201)
jid = job["job_id"]
req("POST", "/api/jobs", {"project_id":pid,"geofence_revision":rid,"paper":"A4","orientation":"landscape","edition":"audit-01"},headers=OP,expect=409)
req("POST", f"/api/jobs/{jid}/run",headers=OP)
req("POST", f"/api/jobs/{jid}/run",headers=OP,expect=409)
done = await_state(jid)
print("PASS: project, geofence, deduplication and REAL Celery execution",done["status"], flush=True)
qa = req("GET",f"/api/jobs/{jid}/artifacts/qa-report.json",headers=REV)
manifest = req("GET",f"/api/jobs/{jid}/artifacts/manifest.json",headers=OP)
pdf = req("GET",f"/api/jobs/{jid}/artifacts/proof.pdf",headers=REV,binary=True)
import hashlib
assert qa["passed"] and qa["blocker_count"] == 0,qa
assert pdf.startswith(b"%PDF-")
assert hashlib.sha256(pdf).hexdigest() == manifest["outputs"]["proof_pdf"]["sha256"]
for fname in ("thumb.png","qa-report.md"):
    assert req("GET",f"/api/jobs/{jid}/artifacts/{fname}",headers=OP,binary=True)
print("PASS: governed artifacts, QA gate, hash verification", flush=True)
req("POST",f"/api/jobs/{jid}/approve",{"reviewer":"forged-identity","comment":"audit only"},headers=OP,expect=403)
approved=req("POST",f"/api/jobs/{jid}/approve",{"reviewer":"forged-identity","comment":"audit only"},headers=REV)
assert approved["reviewer"] != "forged-identity",approved
req("POST",f"/api/jobs/{jid}/approve",{"comment":"duplicate"},headers=REV,expect=409)
repro=req("POST",f"/api/jobs/{jid}/reproduce",headers=OP)
assert repro["matched"] is True,repro
print("PASS: reviewer separation, approvals, immutable finalisation, reproducibility",flush=True)
fixture=Path("tests/fixtures/corrections/valid_corrections.yaml").read_text()
child=req("POST",f"/api/jobs/{jid}/corrections",{"yaml_content":fixture,"author":"audit"},headers=OP,expect=201)
cid=child["job_id"]
req("POST",f"/api/jobs/{cid}/run",headers=OP)
await_state(cid)
print("PASS: correction child job end to end",flush=True)
print(json.dumps({"result":"PASSED","original_job":jid,"child_job":cid,"sha256":hashlib.sha256(pdf).hexdigest()}),flush=True)

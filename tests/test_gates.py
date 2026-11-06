"""Gate tests — run each in fresh process: python3 tests/test_gates.py <name>"""
import json, os, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="sa-gate-")
from __init__ import handle_create, handle_trigger_chain, handle_status, _on_session_start

def _create(prefix):
    return json.loads(handle_create({"name":f"gate-{prefix}","steps":[
        {"job_id":f"{prefix}-s1","cron_job_id":"cron1"},
        {"job_id":f"{prefix}-s2","cron_job_id":"cron2","depends_on":f"{prefix}-s1"},
    ]}))

def test_duplicate():
    r=_create("dup"); assert r["ok"], r
    d=json.loads(handle_trigger_chain({"job_id":"dup-s2"}))
    assert not d["ok"] and "not ready" in d["error"], d
    d=json.loads(handle_trigger_chain({"job_id":"dup-s1"}))
    assert d["ok"] and d["status"]=="running", d
    d2=json.loads(handle_trigger_chain({"job_id":"dup-s1"}))
    assert not d2["ok"] and "already running" in d2["error"], d2
    d=json.loads(handle_trigger_chain({"job_id":"dup-s1","verified_success":True}))
    assert d["ok"] and d["status"]=="succeeded" and "dup-s2" in d["unlocked"], d
    d2=json.loads(handle_trigger_chain({"job_id":"dup-s1","verified_success":True}))
    assert not d2["ok"] and "already succeeded" in d2["error"], d2
    s=json.loads(handle_status({})); st={j["job_id"]:j["status"] for j in s["jobs"]}
    assert st["dup-s2"]=="ready" and st["dup-s1"]=="succeeded", st
    print("duplicate OK", st)

def test_restart():
    r=_create("rst"); assert r["ok"]
    json.loads(handle_trigger_chain({"job_id":"rst-s1"}))
    _on_session_start()
    s=json.loads(handle_status({})); st={j["job_id"]:j["status"] for j in s["jobs"]}
    assert st["rst-s1"]=="ready", st
    assert st["rst-s2"]=="pending", st
    print("restart OK", st)

def test_concurrent():
    r=_create("con"); assert r["ok"]
    results=[]
    def go(): results.append(json.loads(handle_trigger_chain({"job_id":"con-s1"})))
    th=[threading.Thread(target=go) for _ in range(5)]
    [t.start() for t in th]; [t.join() for t in th]
    ok=[x for x in results if x.get("ok")]
    assert len(ok)==1, results
    print("concurrent OK, winners=1")

def test_dep_failure():
    r=_create("dep"); assert r["ok"]
    # mark s1 failed directly via DB? simulate by never succeeding: s2 trigger must stay blocked
    d=json.loads(handle_trigger_chain({"job_id":"dep-s2"}))
    assert not d["ok"], d
    print("dep_failure OK")

if __name__=="__main__":
    fn = sys.argv[1] if len(sys.argv)>1 else "duplicate"
    globals()[f"test_{fn}"]()

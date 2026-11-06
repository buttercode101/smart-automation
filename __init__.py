"""__init__.py — Smart Automation Orchestrator (manual chain-runner).

Design locked after red-team F1-F4:
- F1: NO automatic cron-completion hook (does not exist). Chains advance ONLY
  via orchestrator_trigger_chain after verified success. Copy is honest about this.
- F2: Desktop backend is read-only GETs. All mutations go through these tools
  so the Hermes approval system fires.
- F3: Dashboard backend lives at dashboard/plugin_api.py + dashboard/manifest.json.
- F4: plugin.yaml declares exactly the tools+hooks registered here.
"""
from __future__ import annotations

import json
import time
import uuid

# Relative imports work when loaded as a plugin package; fall back for tests.
try:
    from .storage import init_db, open_db, recompute_readiness, detect_cycle
    from .graph import validate_edges
    from .calendar import has_free_slot
except ImportError:
    from storage import init_db, open_db, recompute_readiness, detect_cycle
    from graph import validate_edges
    from calendar import has_free_slot

_ctx = None  # captured at register() for tool handlers


def _data_dir():
    if _ctx is not None:
        return _ctx.state.data_dir
    import os
    from pathlib import Path
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "plugin-data" / "smart-automation"


def _db():
    conn = open_db(_data_dir())
    init_db(conn)
    return conn


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- tools

def handle_create(args=None, **kw):
    args = args or {}
    name = (args.get("name") or "").strip()
    steps = args.get("steps") or []
    if not name:
        return json.dumps({"ok": False, "error": "name is required"})
    if not steps:
        return json.dumps({"ok": False, "error": "steps[] is required (at least one step)"})
    # steps: [{job_id?, cron_job_id?, depends_on?, calendar_rule?}]
    edges = {}
    normalized = []
    for i, s in enumerate(steps):
        jid = s.get("job_id") or f"step_{i+1}"
        edges[jid] = s.get("depends_on")
        normalized.append({**s, "job_id": jid})
    ok, msg = validate_edges(edges)
    if not ok:
        return json.dumps({"ok": False, "error": msg})
    chain_id = "chain_" + uuid.uuid4().hex[:8]
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO chains(chain_id,name,created_at,updated_at) VALUES(?,?,?,?)",
            (chain_id, name, _now(), _now()),
        )
        for i, s in enumerate(normalized):
            conn.execute(
                "INSERT INTO jobs(job_id,chain_id,cron_job_id,step_order,depends_on,status,calendar_rule) VALUES(?,?,?,?,?,?,?)",
                (s["job_id"], chain_id, s.get("cron_job_id"), i, s.get("depends_on"), "pending", s.get("calendar_rule")),
            )
        conn.commit()
        unlocked = recompute_readiness(conn, chain_id)
        return json.dumps({"ok": True, "chain_id": chain_id, "name": name, "steps": len(normalized), "ready": unlocked})
    finally:
        conn.close()


def handle_status(args=None, **kw):
    args = args or {}
    chain_id = args.get("chain_id")
    conn = _db()
    try:
        q = "SELECT * FROM jobs WHERE chain_id=? ORDER BY step_order" if chain_id else "SELECT * FROM jobs ORDER BY chain_id, step_order"
        params = (chain_id,) if chain_id else ()
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        return json.dumps({"ok": True, "jobs": rows})
    finally:
        conn.close()


def handle_graph(args=None, **kw):
    args = args or {}
    chain_id = args.get("chain_id")
    if not chain_id:
        return json.dumps({"ok": False, "error": "chain_id is required"})
    conn = _db()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM jobs WHERE chain_id=? ORDER BY step_order", (chain_id,)
        ).fetchall()]
        nodes = [{"id": r["job_id"], "status": r["status"], "cron_job_id": r["cron_job_id"]} for r in rows]
        edges = [{"from": r["depends_on"], "to": r["job_id"]} for r in rows if r["depends_on"]]
        return json.dumps({"ok": True, "chain_id": chain_id, "nodes": nodes, "edges": edges})
    finally:
        conn.close()


def handle_trigger_chain(args=None, **kw):
    """Manual chain advance (F1 fix). Verifies deps succeeded, optionally
    checks calendar rule, marks job running. Does NOT execute the cron job
    itself — the agent runs the underlying cronjob via the normal tool path
    so approvals fire."""
    args = args or {}
    job_id = args.get("job_id")
    verified_success = bool(args.get("verified_success"))
    if not job_id:
        return json.dumps({"ok": False, "error": "job_id is required"})
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return json.dumps({"ok": False, "error": f"unknown job {job_id!r}"})
        dep = row["depends_on"]
        if dep:
            dep_row = conn.execute("SELECT status FROM jobs WHERE job_id=?", (dep,)).fetchone()
            if not dep_row or dep_row["status"] != "succeeded":
                return json.dumps({"ok": False, "error": f"blocked: dependency {dep!r} has not succeeded (status={dep_row['status'] if dep_row else 'missing'})"})
        if row["status"] == "paused":
            return json.dumps({"ok": False, "error": f"job {job_id!r} is paused — resume via orchestrator tools, not Desktop POST"})
        if row["calendar_rule"] and args.get("after_iso"):
            free, warn = has_free_slot(row["calendar_rule"], args["after_iso"])
            if not free:
                return json.dumps({"ok": False, "error": warn or "calendar busy"})
        if verified_success:
            conn.execute("UPDATE jobs SET status='succeeded', last_run_at=?, last_result='verified_success' WHERE job_id=?", (_now(), job_id))
            chain_id = row["chain_id"]
        else:
            conn.execute("UPDATE jobs SET status='running', last_run_at=? WHERE job_id=?", (_now(), job_id))
            chain_id = row["chain_id"]
        conn.commit()
        unlocked = recompute_readiness(conn, chain_id) if verified_success else []
        return json.dumps({"ok": True, "job_id": job_id, "status": "succeeded" if verified_success else "running", "unlocked": unlocked})
    finally:
        conn.close()


# ---------------------------------------------------------------- hooks

def _on_post_tool_call(tool_name="", args=None, **kwargs):
    """Observer only (F1): log cronjob_manage results. Never mutates chain state.
    Fail-open."""
    try:
        if tool_name and "cron" in tool_name.lower():
            conn = _db()
            try:
                conn.execute(
                    "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (f"last_cron_tool:{tool_name}", _now()),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass  # fail-open


def _on_session_start(**kwargs):
    try:
        conn = _db()
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------- register

def register(ctx):
    global _ctx
    _ctx = ctx

    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("on_session_start", _on_session_start)

    base = {"type": "object", "properties": {}, "required": []}
    ctx.register_tool(
        name="orchestrator_create", toolset="smart_automation",
        schema={**base, "properties": {
            "name": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "job_id": {"type": "string"}, "cron_job_id": {"type": "string"},
                "depends_on": {"type": "string"}, "calendar_rule": {"type": "string"}}}},
        }, "required": ["name", "steps"]},
        handler=handle_create, emoji="🔗",
    )
    ctx.register_tool(
        name="orchestrator_status", toolset="smart_automation",
        schema={**base, "properties": {"chain_id": {"type": "string"}}},
        handler=handle_status, emoji="📊",
    )
    ctx.register_tool(
        name="orchestrator_graph", toolset="smart_automation",
        schema={**base, "properties": {"chain_id": {"type": "string"}}, "required": ["chain_id"]},
        handler=handle_graph, emoji="🕸️",
    )
    ctx.register_tool(
        name="orchestrator_trigger_chain", toolset="smart_automation",
        schema={**base, "properties": {
            "job_id": {"type": "string"}, "verified_success": {"type": "boolean"},
            "after_iso": {"type": "string"}},
            "required": ["job_id"]},
        handler=handle_trigger_chain, emoji="▶️",
    )

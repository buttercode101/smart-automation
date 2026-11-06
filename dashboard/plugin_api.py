"""dashboard/plugin_api.py — READ-ONLY GET endpoints (F2 fix).

Mounted under /api/plugins/smart-automation/ by the dashboard web server.
No POST/PUT/DELETE: all mutations go through orchestrator_* agent tools so
Hermes approvals fire. A Desktop POST here would bypass approvals (Rule 12).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()


def _db_path():
    import os
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    return home / "plugin-data" / "smart-automation" / "smart_automation.db"


def _rows(sql, args=()):
    p = _db_path()
    if not p.exists():
        return []
    conn = sqlite3.connect(str(p), check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


@router.get("/status")
def status():
    return {"ok": True, "jobs": _rows("SELECT * FROM jobs ORDER BY chain_id, step_order")}


@router.get("/graph")
def graph(chain_id: str = ""):
    if not chain_id:
        return {"ok": False, "error": "chain_id query param required"}
    rows = _rows("SELECT * FROM jobs WHERE chain_id=? ORDER BY step_order", (chain_id,))
    nodes = [{"id": r["job_id"], "status": r["status"], "cron_job_id": r["cron_job_id"]} for r in rows]
    edges = [{"from": r["depends_on"], "to": r["job_id"]} for r in rows if r["depends_on"]]
    return {"ok": True, "chain_id": chain_id, "nodes": nodes, "edges": edges}

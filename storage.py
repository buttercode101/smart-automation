"""storage.py — SQLite graph store inside ctx.state.data_dir.

Schema v1:
  chains(chain_id TEXT PK, name TEXT, created_at TEXT, updated_at TEXT)
  jobs(job_id TEXT PK, chain_id TEXT, cron_job_id TEXT, step_order INT,
       depends_on TEXT, status TEXT, last_run_at TEXT, last_result TEXT,
       calendar_rule TEXT)
  meta(key TEXT PK, value TEXT)

Status values: pending | ready | running | succeeded | failed | paused | blocked
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA_VERSION = 1
_lock = threading.RLock()


def open_db(data_dir):
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    db_path = p / "smart_automation.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
    return conn


def init_db(conn):
    with _lock:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chains(
              chain_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs(
              job_id TEXT PRIMARY KEY,
              chain_id TEXT NOT NULL REFERENCES chains(chain_id),
              cron_job_id TEXT,
              step_order INT NOT NULL,
              depends_on TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              last_run_at TEXT,
              last_result TEXT,
              calendar_rule TEXT
            );
            CREATE TABLE IF NOT EXISTS meta(
              key TEXT PRIMARY KEY,
              value TEXT
            );
            """
        )
        conn.commit()


def detect_cycle(edges):
    """edges: dict node -> [deps]. Returns cycle list or None.

    DFS with recursion stack; deterministic order for stable errors.
    """
    visited = set()
    stack = []
    on_stack = set()

    def dfs(node):
        visited.add(node)
        stack.append(node)
        on_stack.add(node)
        for dep in sorted(edges.get(node, [])):
            if dep not in edges and dep not in visited:
                continue
            if dep in on_stack:
                idx = stack.index(dep)
                return stack[idx:] + [dep]
            if dep not in visited:
                r = dfs(dep)
                if r:
                    return r
        stack.pop()
        on_stack.discard(node)
        return None

    for n in sorted(edges):
        if n not in visited:
            r = dfs(n)
            if r:
                return r
    return None


def recompute_readiness(conn, chain_id):
    """Set status=ready for pending jobs whose deps all succeeded.
    Returns list of job_ids newly unlocked. Does NOT run anything."""
    with _lock:
        cur = conn.execute(
            "SELECT job_id, depends_on, status FROM jobs WHERE chain_id=?",
            (chain_id,),
        )
        rows = cur.fetchall()
        status = {r["job_id"]: r["status"] for r in rows}
        unlocked = []
        for r in rows:
            if r["status"] != "pending":
                continue
            dep = r["depends_on"]
            if not dep:
                conn.execute(
                    "UPDATE jobs SET status='ready' WHERE job_id=?", (r["job_id"],)
                )
                unlocked.append(r["job_id"])
            else:
                dep_status = status.get(dep)
                if dep_status == "succeeded":
                    conn.execute(
                        "UPDATE jobs SET status='ready' WHERE job_id=?", (r["job_id"],)
                    )
                    unlocked.append(r["job_id"])
        conn.commit()
        return unlocked

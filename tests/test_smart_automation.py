import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from storage import open_db, init_db, detect_cycle, recompute_readiness
from graph import validate_edges
from ics_calendar import has_free_slot
import tempfile
import os


def test_cycle_detection():
    assert detect_cycle({"a": ["b"], "b": ["a"]}) == ["a", "b", "a"]
    assert detect_cycle({"a": ["b"], "b": []}) is None
    print("test_cycle_detection OK")


def test_validate_edges():
    ok, _ = validate_edges({"a": None, "b": "a"})
    assert ok
    ok, msg = validate_edges({"a": "missing"})
    assert not ok and "Unknown" in msg
    ok, msg = validate_edges({"a": "b", "b": "a"})
    assert not ok and "cycle" in msg.lower()
    print("test_validate_edges OK")


def test_storage_and_readiness():
    with tempfile.TemporaryDirectory() as d:
        conn = open_db(d)
        init_db(conn)
        conn.execute("INSERT INTO chains VALUES('c1','test','t','t')")
        conn.execute("INSERT INTO jobs(job_id,chain_id,cron_job_id,step_order,depends_on,status) VALUES('s1','c1','cron1',0,NULL,'pending')")
        conn.execute("INSERT INTO jobs(job_id,chain_id,cron_job_id,step_order,depends_on,status) VALUES('s2','c1','cron2',1,'s1','pending')")
        conn.commit()
        unlocked = recompute_readiness(conn, "c1")
        assert unlocked == ["s1"], unlocked
        conn.execute("UPDATE jobs SET status='succeeded' WHERE job_id='s1'")
        conn.commit()
        unlocked = recompute_readiness(conn, "c1")
        assert unlocked == ["s2"], unlocked
        conn.close()
    print("test_storage_and_readiness OK")


def test_calendar_fallback():
    free, warn = has_free_slot("", "2026-11-06T08:00:00Z")
    assert not free and warn
    free, warn = has_free_slot("/nonexistent.ics", "2026-11-06T08:00:00Z")
    assert not free and warn
    print("test_calendar_fallback OK")


if __name__ == "__main__":
    test_cycle_detection()
    test_validate_edges()
    test_storage_and_readiness()
    test_calendar_fallback()
    print("ALL TESTS PASS")

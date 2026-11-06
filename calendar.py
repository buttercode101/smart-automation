"""calendar.py — local ICS free-slot check (read-only, stdlib only).

Parses a local .ics file for VEVENT DTSTART/DTEND, returns whether a
proposed window overlaps any event. Never fetches network calendars.
Unparseable/missing file => (False, warning) so caller falls back to
pure schedule mode with a visible warning (F2 fix: explicit fallback).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


def _parse_ics(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return [], f"calendar unreadable: {e}"
    events = []
    # Very small VEVENT parser — DTSTART/DTEND only, UTC or floating.
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        start = re.search(r"DTSTART[^:\n]*:([^\n]+)", block)
        end = re.search(r"DTEND[^:\n]*:([^\n]+)", block)
        if start and end:
            events.append((start.group(1).strip(), end.group(1).strip()))
    return events, None


def _to_dt(s: str):
    s = s.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def has_free_slot(ics_path: str, after_iso: str):
    """after_iso: ISO8601. Returns (free: bool, warning: str|None)."""
    if not ics_path:
        return False, "no calendar configured — pure schedule mode"
    p = Path(ics_path).expanduser()
    if not p.exists():
        return False, f"calendar file not found: {ics_path} — pure schedule mode"
    events, err = _parse_ics(p)
    if err:
        return False, err + " — pure schedule mode"
    try:
        after = datetime.fromisoformat(after_iso.replace("Z", "+00:00"))
    except ValueError:
        return False, f"bad after_iso {after_iso!r} — pure schedule mode"
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    for s_raw, e_raw in events:
        s, e = _to_dt(s_raw), _to_dt(e_raw)
        if s and e and s <= after < e:
            return False, f"calendar busy at {after_iso} (event {s_raw}–{e_raw})"
    return True, None

"""calendar.py — local ICS free-slot check (read-only, stdlib only).

Handles TZID (zoneinfo, DST-aware), UTC Z, floating (UTC), malformed ICS
-> (False, warning) fallback, never crash. Overlapping events -> busy.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore


def _parse_dt_params(raw_line: str):
    if ":" not in raw_line:
        return None, None
    left, value = raw_line.split(":", 1)
    tzid = None
    m = re.search(r"TZID=([^;:]+)", left)
    if m:
        tzid = m.group(1).strip()
    return value.strip(), tzid


def _to_dt(value: str, tzid: str | None):
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1]
        try:
            return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    dt = None
    for f in ("%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(s, f)
            break
        except ValueError:
            continue
    if dt is None:
        return None
    if tzid and ZoneInfo is not None:
        try:
            return dt.replace(tzinfo=ZoneInfo(tzid)).astimezone(timezone.utc)
        except Exception:
            return None
    return dt.replace(tzinfo=timezone.utc)


def _parse_ics(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return None, f"calendar unreadable: {e}"
    if "BEGIN:VEVENT" not in text:
        return [], None
    events = []
    malformed = 0
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        start_line = re.search(r"DTSTART[^\n]*", block)
        end_line = re.search(r"DTEND[^\n]*", block)
        if not start_line or not end_line:
            malformed += 1
            continue
        sv, stz = _parse_dt_params(start_line.group(0))
        ev, etz = _parse_dt_params(end_line.group(0))
        s = _to_dt(sv, stz) if sv else None
        e = _to_dt(ev, etz) if ev else None
        if s is None or e is None:
            malformed += 1
            continue
        events.append((s, e))
    if malformed and not events:
        return None, f"malformed ICS: {malformed} unparseable event(s) — pure schedule mode"
    return events, None


def has_free_slot(ics_path: str, after_iso: str):
    """after_iso: ISO8601 (offset or Z). Returns (free, warning)."""
    if not ics_path:
        return False, "no calendar configured — pure schedule mode"
    p = Path(ics_path).expanduser()
    if not p.exists():
        return False, f"calendar file not found: {ics_path} — pure schedule mode"
    events, err = _parse_ics(p)
    if err:
        return False, err
    if events is None:
        return False, "malformed ICS — pure schedule mode"
    try:
        after = datetime.fromisoformat(after_iso.replace("Z", "+00:00"))
    except ValueError:
        return False, f"bad after_iso {after_iso!r} — pure schedule mode"
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    after_utc = after.astimezone(timezone.utc)
    for s, e in events:
        if s <= after_utc < e:
            return False, f"calendar busy at {after_iso} (event {s.isoformat()}–{e.isoformat()} UTC)"
    return True, None

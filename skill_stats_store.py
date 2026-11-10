"""Persistence + stats API for skill-stats.

Storage (profile-safe, JSON, atomic replace):

    $HERMES_HOME/skill-stats/global.json
    $HERMES_HOME/skill-stats/sessions/<session_id>.json

Override the data dir with ``SKILL_STATS_DIR`` (absolute path); the legacy
``SKILL_ANALYTICS_DIR`` name is still honored as a fallback.

Each stats file looks like::

    {
      "skills": {"hermes-agent": {"loads": 3, "last_used": 173..., "events": [173...]}},
      "total_loads": 5,
      "updated_at": 173...
    }

``events`` is the timestamped time series behind the charts (capped at
``MAX_EVENTS_PER_SKILL``; pre-v1.3 counters use the legacy ``count`` key and
are migrated on read — charts show recorded events only, never fabricated history).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()

MAX_EVENTS_PER_SKILL = 1000


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home()
    except Exception:
        return Path(os.environ.get("HERMES_HOME", "")).expanduser() or Path.home() / ".hermes"


def _data_dir() -> Path:
    override = os.environ.get("SKILL_STATS_DIR", "").strip() or os.environ.get("SKILL_ANALYTICS_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return _hermes_home() / "skill-stats"


def _global_path(data_dir: Optional[Path] = None) -> Path:
    return (data_dir or _data_dir()) / "global.json"


def _session_path(session_id: str, data_dir: Optional[Path] = None) -> Path:
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (session_id or "default"))
    return (data_dir or _data_dir()) / "sessions" / f"{safe}.json"


def _empty_stats() -> dict[str, Any]:
    return {"skills": {}, "total_loads": 0, "updated_at": 0}


def _migrate_entry(v: dict[str, Any]) -> dict[str, Any]:
    """Rename legacy ``count`` -> ``loads`` (pre-v1.3 data) on read."""
    if "loads" not in v and "count" in v:
        v["loads"] = int(v.get("count") or 0)
    v.setdefault("loads", 0)
    v.setdefault("last_used", 0)
    v.setdefault("events", [])
    return v


def _load_stats(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("skills"), dict):
            for v in doc["skills"].values():
                if isinstance(v, dict):
                    _migrate_entry(v)
            doc.setdefault("total_loads", sum(int(v.get("loads") or 0) for v in doc["skills"].values() if isinstance(v, dict)))
            return doc
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("skill-stats: failed to read %s: %s", path, e)
    return _empty_stats()


def _save_stats(path: Path, stats: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stats["updated_at"] = int(time.time())
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(stats, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        logger.debug("skill-stats: failed to write %s: %s", path, e)


def _bump(stats: dict[str, Any], skill_name: str, now: Optional[int] = None) -> dict[str, Any]:
    if not skill_name:
        return stats
    now = now or int(time.time())
    entry = stats.setdefault("skills", {}).setdefault(skill_name, {"loads": 0, "last_used": now, "events": []})
    entry["loads"] = int(entry.get("loads") or 0) + 1
    entry["last_used"] = now
    events = entry.setdefault("events", [])
    events.append(now)
    del events[:-MAX_EVENTS_PER_SKILL]  # cap: drop oldest
    stats["total_loads"] = int(stats.get("total_loads") or 0) + 1
    return stats


def record_usage(skill_name: str, session_id: str = "", data_dir: Optional[Path] = None) -> None:
    """Increment global + session counters for one skill use."""
    if not skill_name:
        return
    with _lock:
        gpath = _global_path(data_dir)
        _save_stats(gpath, _bump(_load_stats(gpath), skill_name))
        if session_id:
            spath = _session_path(session_id, data_dir)
            _save_stats(spath, _bump(_load_stats(spath), skill_name))


def _last_stats_date(stats: dict[str, Any]) -> str:
    """``YYYY-MM-DD`` of the most recent recorded activity (fallback: file updated_at)."""
    best = 0
    for v in (stats.get("skills") or {}).values():
        if isinstance(v, dict):
            best = max(best, int(v.get("last_used") or 0))
    ts = best or int(stats.get("updated_at") or 0)
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def get_stats(scope: str = "global", session_id: str = "", data_dir: Optional[Path] = None) -> dict[str, Any]:
    """Return sorted stats for `scope` ("global" or "session").

    Each skill row carries ``loads`` (cumulative counter). Returns
    ``total_loads``, ``unique_skills``, ``skills`` and ``last_stats``.
    """
    if scope == "session":
        stats = _load_stats(_session_path(session_id, data_dir))
    else:
        stats = _load_stats(_global_path(data_dir))
    rows: list[dict[str, Any]] = []
    for name, v in (stats.get("skills") or {}).items():
        if not isinstance(v, dict):
            continue
        entry = _migrate_entry(v)
        rows.append({"skill": name, "loads": int(entry.get("loads") or 0), "last_used": int(entry.get("last_used") or 0)})
    rows.sort(key=lambda r: (-r["loads"], r["skill"]))
    unique = len([r for r in rows if int(r.get("loads") or 0) > 0])
    return {
        "scope": scope,
        "session_id": session_id if scope == "session" else "",
        "total_loads": int(stats.get("total_loads") or sum(int(r.get("loads") or 0) for r in rows)),
        "unique_skills": unique,
        "skills": rows,
        "updated_at": int(stats.get("updated_at", 0)),
        "last_stats": _last_stats_date(stats),
    }


def format_stats(stats: dict[str, Any]) -> str:
    title = f"skill-stats — {stats['scope']}" + (f" ({stats['session_id']})" if stats.get("session_id") else "")
    last_stats = str(stats.get("last_stats") or "")
    lines = [title, f"total loads: {stats['total_loads']} · unique skills: {stats['unique_skills']} · last stats: {last_stats}"]
    if not stats["skills"]:
        lines.append("(no skill loads recorded yet)")
        return "\n".join(lines)
    lines.append(f"{'skill':<40} {'loads':>5}  last_used")
    for r in stats["skills"]:
        last = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["last_used"])) if r["last_used"] else "-"
        lines.append(f"{r['skill']:<40} {r['loads']:>5}  {last}")
    return "\n".join(lines)


def reset_stats(scope: str = "global", session_id: str = "", data_dir: Optional[Path] = None) -> None:
    with _lock:
        if scope == "session":
            _session_path(session_id, data_dir).unlink(missing_ok=True)
        else:
            _global_path(data_dir).unlink(missing_ok=True)
            sessions = (data_dir or _data_dir()) / "sessions"
            if sessions.exists():
                for p in sessions.glob("*.json"):
                    p.unlink(missing_ok=True)


def get_series(skill_name: str, days: int = 30, scope: str = "global",
               session_id: str = "", data_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """Daily buckets for one skill: ``[{date: YYYY-MM-DD, loads: n}, ...]`` (oldest first).

    Derived from the timestamped ``events`` log; ``days`` trailing days ending today.
    Empty when the skill has no recorded events in the window.
    """
    from datetime import date, timedelta

    stats = _load_stats(_session_path(session_id, data_dir) if scope == "session" else _global_path(data_dir))
    entry = (stats.get("skills") or {}).get(skill_name) or {}
    events = entry.get("events") or []
    today = date.today()
    buckets = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days)}
    for ts in events:
        try:
            day = time.strftime("%Y-%m-%d", time.localtime(int(ts)))
        except Exception:
            continue
        if day in buckets:
            buckets[day] += 1
    return [{"date": d, "loads": buckets[d]} for d in sorted(buckets)]


def get_series_all(days: int = 30, scope: str = "global",
                   session_id: str = "", data_dir: Optional[Path] = None) -> dict[str, list[dict[str, Any]]]:
    """Series for every skill that has recorded events (dashboard table + charts)."""
    stats = _load_stats(_session_path(session_id, data_dir) if scope == "session" else _global_path(data_dir))
    out = {}
    for name in (stats.get("skills") or {}):
        series = get_series(name, days=days, scope=scope, session_id=session_id, data_dir=data_dir)
        if any(r["loads"] for r in series):
            out[name] = series
    return out

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

VERSION = "0.9.1"

MAX_EVENTS_PER_SKILL = 1000

#: Period options (in days) offered by every surface. Index + 1 = shortcut key.
PERIOD_OPTIONS = (1, 3, 7, 30, 60, 90)
DEFAULT_DAYS = 1
DEFAULT_LIMIT = 10


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


def _safe_name(session_id: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (session_id or "default"))


def _session_path(session_id: str, data_dir: Optional[Path] = None) -> Path:
    return (data_dir or _data_dir()) / "sessions" / f"{_safe_name(session_id)}.json"


def _lookup_session_by_title(query: str) -> str:
    """Look a session title/display_name up in Hermes' own state DB (read-only).

    Exact match first, then a prefix match; the most recently active wins.
    Returns the session id (``chat_id`` or ``id``) or "" when nothing matches
    or the DB is unavailable/shaped differently.
    """
    db_path = _hermes_home() / "state.db"
    if not db_path.exists():
        return ""
    try:
        import sqlite3

        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            for clause, params in (
                ("title = ? OR display_name = ?", (query, query)),
                ("title LIKE ? OR display_name LIKE ?", (f"{query}%", f"{query}%")),
            ):
                try:
                    row = con.execute(
                        f"SELECT id, chat_id FROM sessions WHERE {clause} "
                        "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 1",
                        params,
                    ).fetchone()
                except sqlite3.Error:
                    continue  # older schema without these columns
                if row and (row[1] or row[0]):
                    return str(row[1] or row[0])
        finally:
            con.close()
    except Exception as e:
        logger.debug("skill-stats: title lookup for %r failed: %s", query, e)
    return ""


def resolve_session_id(query: str, data_dir: Optional[Path] = None) -> tuple[str, str]:
    """Resolve a ``--session`` value to a stored session id.

    Accepts, in order: an exact session id, a unique id **prefix** (short
    forms like ``local-c12c3f0c1d37f66b``; the most recently written file wins
    when several ids share the prefix), or a session **title/display_name**
    recorded in Hermes' state DB (``stageshow-bentora``). Returns
    ``(session_id, how)`` with ``how`` one of ``"exact"``, ``"prefix"``,
    ``"title"`` or ``"none"`` (empty id).
    """
    if not query:
        return "", "none"
    sdir = (data_dir or _data_dir()) / "sessions"
    if (sdir / f"{_safe_name(query)}.json").exists():
        return query, "exact"
    try:
        matches = [p for p in sdir.glob("*.json") if p.stem.startswith(query)]
    except OSError:
        matches = []
    if matches:
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return matches[0].stem, "prefix"
    resolved = _lookup_session_by_title(query)
    if resolved:
        return resolved, "title"
    return "", "none"


def _pins_path(data_dir: Optional[Path] = None) -> Path:
    return (data_dir or _data_dir()) / "pins.json"


def _empty_stats() -> dict[str, Any]:
    return {"skills": {}, "total_loads": 0, "updated_at": 0}


def skill_categories(home: Optional[Path] = None) -> dict[str, str]:
    """Map skill name -> category from the profile's skills directory.

    Layout: ``<skills>/<category>/<skill>/SKILL.md`` → the skill's category is
    ``<category>``; ``<skills>/<skill>/SKILL.md`` → category "" (no category
    folder). Hidden directories (dot-prefixed, e.g. ``.archive``) are ignored.
    Skills with no folder (plugin-provided, namespaced names) resolve to "".
    """
    base = (home or _hermes_home()) / "skills"
    out: dict[str, str] = {}
    try:
        for entry in base.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if (entry / "SKILL.md").is_file():
                out[entry.name] = ""
                continue
            for sub in entry.iterdir():
                if sub.is_dir() and not sub.name.startswith(".") and (sub / "SKILL.md").is_file():
                    out[sub.name] = entry.name
    except OSError as e:
        logger.debug("skill-stats: cannot scan skills dir %s: %s", base, e)
    return out


def get_pins(data_dir: Optional[Path] = None) -> list[str]:
    """Pinned skill names (dashboard monitoring), in pin order."""
    try:
        doc = json.loads(_pins_path(data_dir).read_text(encoding="utf-8"))
        if isinstance(doc, dict):
            return [str(s) for s in doc.get("pins", []) if isinstance(s, str)]
        if isinstance(doc, list):
            return [str(s) for s in doc if isinstance(s, str)]
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("skill-stats: failed to read pins: %s", e)
    return []


def set_pins(pins: list[str], data_dir: Optional[Path] = None) -> list[str]:
    """Replace the pin list (order-preserving, de-duplicated)."""
    clean: list[str] = []
    for p in pins or []:
        if isinstance(p, str) and p.strip() and p not in clean:
            clean.append(p.strip())
    path = _pins_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps({"pins": clean}, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        logger.debug("skill-stats: failed to write pins: %s", e)
    return clean


def toggle_pin(skill_name: str, data_dir: Optional[Path] = None) -> list[str]:
    """Pin an unpinned skill / unpin a pinned one; returns the new pin list."""
    if not skill_name:
        return get_pins(data_dir)
    pins = get_pins(data_dir)
    if skill_name in pins:
        pins.remove(skill_name)
    else:
        pins.append(skill_name)
    return set_pins(pins, data_dir)


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
               session_id: str = "", data_dir: Optional[Path] = None,
               granularity: Optional[str] = None) -> list[dict[str, Any]]:
    """Buckets for one skill, oldest first: ``[{date, loads}, ...]``.

    ``granularity``: ``"day"`` (default for periods > 3 days) or ``"hour"``
    (default for periods <= 3 days, e.g. the 1d/3d chart x-axis). Hourly
    labels are ``YYYY-MM-DDTHH:00`` in local time.
    """
    stats = _load_stats(_session_path(session_id, data_dir) if scope == "session" else _global_path(data_dir))
    entry = (stats.get("skills") or {}).get(skill_name) or {}
    events = entry.get("events") or []
    days = max(int(days), 1)
    if granularity is None:
        granularity = "hour" if days <= 3 else "day"
    if granularity == "hour":
        now = int(time.time())
        start = now // 3600 * 3600 - (days * 24 - 1) * 3600
        buckets = {}
        order = []
        for i in range(days * 24):
            label = time.strftime("%Y-%m-%dT%H:00", time.localtime(start + i * 3600))
            buckets[label] = 0
            order.append(label)
        for ts in events:
            try:
                label = time.strftime("%Y-%m-%dT%H:00", time.localtime(int(ts)))
            except Exception:
                continue
            if label in buckets:
                buckets[label] += 1
        return [{"date": lbl, "loads": buckets[lbl]} for lbl in order]
    from datetime import date, timedelta

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
                   session_id: str = "", data_dir: Optional[Path] = None,
                   granularity: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
    """Series for every skill that has recorded events (dashboard table + charts)."""
    stats = _load_stats(_session_path(session_id, data_dir) if scope == "session" else _global_path(data_dir))
    out = {}
    for name in (stats.get("skills") or {}):
        series = get_series(name, days=days, scope=scope, session_id=session_id,
                            data_dir=data_dir, granularity=granularity)
        if any(r["loads"] for r in series):
            out[name] = series
    return out


# ── period-scoped display table ─────────────────────────────────────────────

def get_table(scope: str = "global", session_id: str = "", data_dir: Optional[Path] = None,
              days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """Loads within the trailing ``days``-day window, with category and share.

    ``days <= 0`` means all time. Each row: ``skill`` (name as counted),
    ``category`` ("" when the skill has no category folder), ``loads`` (within
    the window), ``pct`` (share of the window's total, 2 decimals),
    ``last_used`` (latest in-window event; 0 when none), ``all_loads``
    (all-time counter, unchanged semantics).
    """
    days = max(int(days), 0)
    stats = _load_stats(_session_path(session_id, data_dir) if scope == "session" else _global_path(data_dir))
    cats = skill_categories()
    since = int(time.time()) - days * 86400 if days > 0 else 0
    rows: list[dict[str, Any]] = []
    for name, v in (stats.get("skills") or {}).items():
        if not isinstance(v, dict):
            continue
        v = _migrate_entry(v)
        events = [int(e) for e in (v.get("events") or []) if isinstance(e, (int, float))]
        window = [e for e in events if e >= since] if days > 0 else list(events)
        loads = len(window) if days > 0 else int(v.get("loads") or 0)
        last_in = max(window) if window else 0
        if not last_in and days <= 0:
            last_in = int(v.get("last_used") or 0)
        rows.append({"skill": name, "category": cats.get(name, ""), "loads": loads,
                     "pct": 0.0, "last_used": last_in, "all_loads": int(v.get("loads") or 0)})
    rows.sort(key=lambda r: (-r["loads"], r["skill"]))
    total = sum(r["loads"] for r in rows)
    for r in rows:
        r["pct"] = round(r["loads"] * 100.0 / total, 2) if total else 0.0
    return {"scope": scope, "session_id": session_id if scope == "session" else "",
            "days": days, "total_loads": total,
            "unique_skills": len([r for r in rows if r["loads"] > 0]),
            "skills": rows}


def group_by_category(table: dict[str, Any]) -> dict[str, Any]:
    """Aggregate a period table by category (pinned to no skill names).

    Rows: ``category`` ("" → "(uncategorized)"), summed ``loads``, recomputed
    ``pct`` and ``last_used`` = latest last-used among the category's skills.
    """
    agg: dict[str, dict[str, Any]] = {}
    for r in table.get("skills", []):
        key = r.get("category") or "(uncategorized)"
        a = agg.setdefault(key, {"loads": 0, "last_used": 0})
        a["loads"] += int(r.get("loads") or 0)
        a["last_used"] = max(a["last_used"], int(r.get("last_used") or 0))
    total = sum(a["loads"] for a in agg.values())
    rows = [{"category": k, "loads": a["loads"],
             "pct": round(a["loads"] * 100.0 / total, 2) if total else 0.0,
             "last_used": a["last_used"]}
            for k, a in sorted(agg.items(), key=lambda kv: (-kv[1]["loads"], kv[0]))]
    return {"scope": table.get("scope", "global"), "session_id": table.get("session_id", ""),
            "days": table.get("days", 1), "total_loads": total,
            "unique_skills": len([r for r in rows if r["loads"] > 0]), "skills": rows}


def save_output(path: str, *, text: Optional[str] = None, data: Optional[dict[str, Any]] = None,
                force_json: bool = False) -> Path:
    """Write ``text`` (or ``data`` as JSON) to ``path``.

    JSON is written when ``force_json`` (``--json``) is set or the file
    extension is ``.json``; otherwise ``text`` is written verbatim. Parent
    directories are created as needed.
    """
    p = Path(path).expanduser()
    if (force_json or p.suffix.lower() == ".json") and data is not None:
        content = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        content = text or ""
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _fmt_ts(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts))) if ts else "-"


def render_table(headers: list[str], rows: list[list[Any]], aligns: Optional[list[str]] = None,
                 bold: bool = False) -> str:
    """PrettyTable-style ASCII table: ``+---+`` borders, ``|`` cells.

    Headers are uppercased; with ``bold=True`` they are additionally wrapped
    in ANSI bold (terminal-only output — never for chat/slash text). Column
    widths fit the widest cell; ``aligns`` holds ``"l"``/``"r"`` per column.
    """
    def clean(cell: Any) -> str:
        return str(cell).replace("\n", " ")

    widths = [len(clean(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(clean(cell)))
            else:
                widths.append(len(clean(cell)))

    def sep() -> str:
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(row: list[Any], bold_cells: bool = False) -> str:
        cells = []
        for i, w in enumerate(widths):
            s = clean(row[i]) if i < len(row) else ""
            a = aligns[i] if aligns and i < len(aligns) else "l"
            padded = s.rjust(w) if a == "r" else s.ljust(w)
            cells.append(f"\033[1m{padded}\033[0m" if bold_cells else padded)
        return "| " + " | ".join(cells) + " |"

    lines = [sep(), fmt([h.upper() for h in headers], bold_cells=bold), sep()]
    lines.extend(fmt(r) for r in rows)
    lines.append(sep())
    return "\n".join(lines)


def format_table(table: dict[str, Any], *, group: bool = False, offset: int = 0,
                 limit: int = DEFAULT_LIMIT, data_dir: Optional[Path] = None,
                 use_ansi: bool = False) -> str:
    """PrettyTable-style ASCII rendering of a period table (CLI + slash)."""
    scope = table.get("scope", "global")
    sid = table.get("session_id") or ""
    days = int(table.get("days", 1))
    title = f"skill-stats — {scope}" + (f" ({sid})" if sid else "") + f" · period: {days}d"
    lines = [title, f"total loads ({days}d): {table.get('total_loads', 0)} · unique skills: {table.get('unique_skills', 0)}"]
    rows = table.get("skills") or []
    if not rows:
        lines.append("(no skill loads recorded in this period)")
        return "\n".join(lines)
    if group:
        headers, aligns = ["Category", "Loads", "%", "Last used"], ["l", "r", "r", "l"]
        out = [[r["category"], r["loads"], f"{r['pct']:.2f}%", _fmt_ts(r["last_used"])] for r in rows]
    else:
        headers, aligns = ["Skill", "Category", "Loads", "%", "Last used"], ["l", "l", "r", "r", "l"]
        out = [[r["skill"], r.get("category") or "", r["loads"], f"{r['pct']:.2f}%", _fmt_ts(r["last_used"])] for r in rows]
    offset = max(int(offset), 0)
    limit = max(int(limit), 1)
    page = out[offset:offset + limit]
    body = render_table(headers, page, aligns, bold=use_ansi)
    lines.append(body)
    shown_end = offset + len(page)
    if shown_end < len(out):
        lines.append(f"({len(out) - shown_end} more rows · use --offset {shown_end})")
    return "\n".join(lines)

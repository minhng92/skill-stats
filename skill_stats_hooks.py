"""Lifecycle hooks + /skill-stats slash command for skill-stats.

Only ``skill_view`` counts as a "use". ``skills_list`` (browsing) and
``skill_manage`` (editing) are not counted. Counting happens in
``pre_tool_call`` (before execution), so a ``skill_view`` that then fails
still counts as an attempted use. Unknown / namespaced skill names are
counted verbatim as given.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from . import skill_stats_charts as _charts
from . import skill_stats_store as _store

_COUNTED_TOOLS = {"skill_view"}


def _extract_skill_name(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("name", "skill", "id", "skill_name"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def on_pre_tool_call(tool_name: str = "", args: Any = None, session_id: str = "", **_: Any) -> Optional[dict[str, str]]:
    if tool_name not in _COUNTED_TOOLS:
        return None
    name = _extract_skill_name(args)
    if name:
        _store.record_usage(name, session_id=str(session_id or ""))
    return None  # never block


def on_session_start(session_id: str = "", **_: Any) -> None:
    if session_id:
        # Ensure the session file exists so "session" scope is queryable
        # from the very first turn.
        with _store._lock:
            p = _store._session_path(str(session_id))
            if not p.exists():
                _store._save_stats(p, _store._empty_stats())


def on_session_end(session_id: str = "", **_: Any) -> None:
    # Session file is kept on disk (history); nothing to flush — writes are
    # atomic per event. Kept as an explicit hook for lifecycle symmetry.
    return None


def _parse_display_args(tokens: list[str]) -> dict[str, Any]:
    """Shared display options for ``/skill-stats`` and ``hermes skill-stats``."""
    opts: dict[str, Any] = {"days": _store.DEFAULT_DAYS, "offset": 0,
                            "limit": _store.DEFAULT_LIMIT, "group": False}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        try:
            if t in ("--day", "-d") and i + 1 < len(tokens):
                i += 1
                opts["days"] = max(int(tokens[i]), 0)
            elif t == "--offset" and i + 1 < len(tokens):
                i += 1
                opts["offset"] = max(int(tokens[i]), 0)
            elif t == "--limit" and i + 1 < len(tokens):
                i += 1
                opts["limit"] = max(int(tokens[i]), 1)
            elif t in ("--group", "--group-by-category"):
                opts["group"] = True
        except ValueError:
            pass  # ignore malformed values, keep defaults
        i += 1
    return opts


def on_skill_stats(raw_args: str = "", session_id: str = "", **_: Any) -> Optional[str]:
    """``/skill-stats`` — this session by default; ``global`` for all-time.

    Options: ``[global] [--json] [reset] [--day N] [--offset N] [--limit N]
    [--group]``. Default period is 1 day; the table is a bordered ASCII table
    with category and percentage columns.
    """
    tokens = (raw_args or "").strip().split()
    as_json = "--json" in tokens
    scope = "global" if "global" in tokens else "session"
    if "reset" in tokens:
        _store.reset_stats(scope, session_id=str(session_id or ""))
        return f"skill-stats: reset {scope} stats."
    opts = _parse_display_args(tokens)
    table = _store.get_table(scope, session_id=str(session_id or ""), days=opts["days"])
    if opts["group"]:
        table = _store.group_by_category(table)
    if as_json:
        table["offset"] = opts["offset"]
        table["limit"] = opts["limit"]
        table["group"] = opts["group"]
        table["series"] = _store.get_series_all(days=max(opts["days"], 1), scope=scope,
                                                session_id=str(session_id or ""))
        return json.dumps(table, indent=2)
    text = _store.format_table(table, group=opts["group"], offset=opts["offset"],
                               limit=opts["limit"])
    rows = table.get("skills") or []
    if rows and not opts["group"]:
        top = rows[0]["skill"]
        series = _store.get_series(top, days=max(opts["days"], 1), scope=scope,
                                   session_id=str(session_id or ""))
        label = f"last {opts['days']}d" if opts["days"] > 0 else "all time"
        if any(r["loads"] for r in series):
            text += f"\n\nTop — {label} (bar):\n" + _charts.render_chart(top, series, "bar")
            text += "\n\nTop — cumulative (line):\n" + _charts.render_chart(top, series, "line")
    return text

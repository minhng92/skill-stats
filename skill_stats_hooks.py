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


def on_skill_stats(raw_args: str = "", session_id: str = "", **_: Any) -> Optional[str]:
    """``/skill-stats`` — this session by default; ``global`` for all-time."""
    tokens = (raw_args or "").strip().split()
    as_json = "--json" in tokens
    scope = "global" if "global" in tokens else "session"
    if "reset" in tokens:
        _store.reset_stats(scope, session_id=str(session_id or ""))
        return f"skill-stats: reset {scope} stats."
    stats = _store.get_stats(scope, session_id=str(session_id or ""))
    if as_json:
        stats["series"] = _store.get_series_all(scope=scope, session_id=str(session_id or ""))
        return json.dumps(stats, indent=2)
    text = _store.format_stats(stats)
    if stats["skills"]:
        top = stats["skills"][0]["skill"]
        series = _store.get_series(top, days=14, scope=scope, session_id=str(session_id or ""))
        if any(r["loads"] for r in series):
            text += "\n\nTop skill — last 14 days (bar):\n" + _charts.render_chart(top, series, "bar")
            text += "\n\nTop skill — cumulative (line):\n" + _charts.render_chart(top, series, "line")
    return text

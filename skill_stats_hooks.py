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


def _parse_display_args(tokens: list[str], default_session: str = "") -> dict[str, Any]:
    """Shared display options for ``/skill-stats`` and ``hermes skill-stats``.

    Scope rule: ``--session``/``-s`` (with an id, or bare inside a session)
    selects session scope; without it the scope is global.
    """
    opts: dict[str, Any] = {"days": _store.DEFAULT_DAYS, "offset": 0,
                            "limit": _store.DEFAULT_LIMIT, "group": False,
                            "session_id": "", "session_explicit": False, "output": ""}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        try:
            if t in ("--day", "-d") and i + 1 < len(tokens):
                i += 1
                opts["days"] = max(int(tokens[i]), 0)
            elif t in ("--offset", "-of") and i + 1 < len(tokens):
                i += 1
                opts["offset"] = max(int(tokens[i]), 0)
            elif t in ("--limit", "-l") and i + 1 < len(tokens):
                i += 1
                opts["limit"] = max(int(tokens[i]), 1)
            elif t in ("--group", "--group-by-category", "-g"):
                opts["group"] = True
            elif t in ("--session", "-s"):
                opts["session_explicit"] = True
                nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
                if nxt and not nxt.startswith("-"):
                    opts["session_id"] = nxt
                    i += 1
                else:
                    opts["session_id"] = default_session  # bare --session = this session
            elif t in ("--output", "-o") and i + 1 < len(tokens):
                i += 1
                opts["output"] = tokens[i]
        except ValueError:
            pass  # ignore malformed values, keep defaults
        i += 1
    opts["scope"] = "session" if opts["session_id"] else "global"
    return opts


def on_skill_stats(raw_args: str = "", session_id: str = "", **_: Any) -> Optional[str]:
    """``/skill-stats`` — the CURRENT session by default (statistics of itself).

    ``global`` switches to all-time stats; ``--session``/``-s <id>`` selects
    another session (an exact id, a short-form id prefix, or a session title).
    Options: ``[global] [--session <id>] [--json] [reset] [--day N] [--offset N]
    [--limit N] [--group] [--output <file>]``. Default period is 1 day; the
    table is a bordered ASCII table with category and percentage columns.
    ``--output``/``-o`` writes the result to a file: JSON when ``--json`` is
    given or the file extension is ``.json``, raw text otherwise.
    """
    tokens = (raw_args or "").strip().split()
    wants_global = "global" in tokens
    tokens = [t for t in tokens if t != "global"]
    opts = _parse_display_args(tokens, default_session=str(session_id or ""))
    if not opts["session_explicit"]:
        # slash default: statistics of ITSELF (the host-injected session id)
        opts["session_id"] = str(session_id or "")
        opts["scope"] = "session" if opts["session_id"] else "global"
    if wants_global and not opts["session_explicit"]:
        # `global` keyword: all-time stats (ignored when --session names one)
        opts["session_id"] = ""
        opts["scope"] = "global"
    scope, sid = opts["scope"], opts["session_id"]
    resolved_note = ""
    if sid:
        sid, how = _store.resolve_session_id(sid)
        if not sid:
            return (f"skill-stats: no session matches {opts['session_id']!r} "
                    "(no exact id, id prefix or title match).")
        if how in ("prefix", "title"):
            resolved_note = f"resolved {opts['session_id']} → {sid} ({how})\n"
    if "reset" in tokens:
        _store.reset_stats(scope, session_id=sid)
        return f"skill-stats: reset {scope} stats."
    table = _store.get_table(scope, session_id=sid, days=opts["days"])
    if opts["group"]:
        table = _store.group_by_category(table)
    use_json = "--json" in tokens or opts["output"].lower().endswith(".json")
    if use_json:
        table["offset"] = opts["offset"]
        table["limit"] = opts["limit"]
        table["group"] = opts["group"]
        table["series"] = _store.get_series_all(days=max(opts["days"], 1), scope=scope,
                                                session_id=sid)
    if opts["output"]:
        if use_json:
            p = _store.save_output(opts["output"], data=table, force_json=True)
        else:
            p = _store.save_output(opts["output"], text=_render_text(table, opts, scope, sid))
        return f"skill-stats: output written to {p}"
    if use_json:
        return json.dumps(table, indent=2)
    return resolved_note + _render_text(table, opts, scope, sid)


def _render_text(table: dict[str, Any], opts: dict[str, Any], scope: str, sid: str) -> str:
    text = _store.format_table(table, group=opts["group"], offset=opts["offset"],
                               limit=opts["limit"])
    rows = table.get("skills") or []
    if rows and not opts["group"]:
        top = rows[0]["skill"]
        series = _store.get_series(top, days=max(opts["days"], 1), scope=scope,
                                   session_id=sid)
        label = f"last {opts['days']}d" if opts["days"] > 0 else "all time"
        if any(r["loads"] for r in series):
            text += f"\n\nTop — {label} (bar):\n" + _charts.render_chart(top, series, "bar")
            text += "\n\nTop — cumulative (line):\n" + _charts.render_chart(top, series, "line")
    return text

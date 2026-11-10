"""``hermes skill-stats`` — global by default; ``--session`` for session scope."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import skill_stats_store as _store


def _add_display_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--day", "-d", type=int, default=_store.DEFAULT_DAYS,
                   help="Statistics period in days (default: 1); 0 = all time")
    p.add_argument("--offset", "-of", type=int, default=0, help="First row to show (default: 0)")
    p.add_argument("--limit", "-l", type=int, default=_store.DEFAULT_LIMIT,
                   help=f"Rows per page (default: {_store.DEFAULT_LIMIT})")
    p.add_argument("--group", "--group-by-category", "-g", dest="group", action="store_true",
                   help="Group statistics by skill category")
    p.add_argument("--output", "-o", default="",
                   help="Write the result to a file (JSON when --json or *.json, raw text otherwise)")


def setup_cli(parser: argparse.ArgumentParser) -> None:
    # Bare `hermes skill-stats` shows global stats (no subcommand needed).
    parser.add_argument("--session", "-s", default="",
                        help="Session ID — selects session scope (default: global)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    _add_display_args(parser)
    sub = parser.add_subparsers(dest="subcommand")
    sp = sub.add_parser("stats", help="Show skill usage statistics (bare call = global)")
    sp.add_argument("--session", "-s", default="")
    sp.add_argument("--json", action="store_true")
    _add_display_args(sp)
    rp = sub.add_parser("reset", help="Reset global statistics (or one session with --session)")
    rp.add_argument("--session", "-s", default="",
                    help="Reset only this session's stats (default: global)")
    rp.add_argument("--yes", action="store_true", help="Confirm reset (no longer required; kept for compat)")
    dp = sub.add_parser("doctor", help="Plugin health check")
    dp.add_argument("--json", action="store_true")


def _print_stats(args: Any, *, use_ansi: bool) -> int:
    session_id = str(getattr(args, "session", "") or "")
    resolved_note = ""
    if session_id:
        session_id, how = _store.resolve_session_id(session_id)
        if not session_id:
            print(f"skill-stats: no session matches {args.session!r} "
                  "(no exact id, id prefix or title match).", file=sys.stderr)
            return 2
        if how in ("prefix", "title"):
            resolved_note = f"resolved {args.session} → {session_id} ({how})"
    scope = "session" if session_id else "global"  # no --session -> global
    days = int(getattr(args, "day", _store.DEFAULT_DAYS))
    offset = int(getattr(args, "offset", 0))
    limit = int(getattr(args, "limit", _store.DEFAULT_LIMIT))
    group = bool(getattr(args, "group", False))
    output = str(getattr(args, "output", "") or "")
    as_json = bool(getattr(args, "json", False))

    table = _store.get_table(scope, session_id=session_id, days=days)
    if group:
        table = _store.group_by_category(table)
    use_json = as_json or (output.lower().endswith(".json"))
    if use_json:
        table["offset"] = offset
        table["limit"] = limit
        table["group"] = group
        table["series"] = _store.get_series_all(days=max(days, 1), scope=scope, session_id=session_id)

    if output:
        if use_json:
            p = _store.save_output(output, data=table, force_json=True)
        else:
            p = _store.save_output(output, text=_store.format_table(
                table, group=group, offset=offset, limit=limit, use_ansi=use_ansi))
        print(f"skill-stats: output written to {p}")
        return 0
    if resolved_note:
        print(resolved_note)
    if use_json:
        print(json.dumps(table, indent=2))
        return 0
    print(_store.format_table(table, group=group, offset=offset, limit=limit, use_ansi=use_ansi))
    return 0


def handle_cli(args: Any) -> int:
    sub = getattr(args, "subcommand", None)
    if sub is None or sub == "stats":
        # Bare `hermes skill-stats` = global stats; --session selects session scope.
        return _print_stats(args, use_ansi=sys.stdout.isatty())
    if sub == "reset":
        session_id = str(getattr(args, "session", "") or "")
        if session_id:
            session_id, _ = _store.resolve_session_id(session_id)
            if not session_id:
                print(f"skill-stats: no session matches {args.session!r}.", file=sys.stderr)
                return 2
        scope = "session" if session_id else "global"
        _store.reset_stats(scope, session_id=session_id)
        print(f"skill-stats: reset {scope} stats.")
        return 0
    if sub == "doctor":
        checks = {
            "plugin": {"name": "skill-stats", "version": _store.VERSION},
            "data_dir": str(_store._data_dir()),
            "global_path": str(_store._global_path()),
            "global_stats": _store.get_stats("global"),
        }
        if getattr(args, "json", False):
            print(json.dumps(checks, indent=2))
        else:
            for k, v in checks.items():
                print(f"{k:>18}: {v}")
        return 0
    print("skill-stats: usage: hermes skill-stats [--session <id>] [--day N] [--offset N] "
          "[--limit N] [--group] [--output FILE] [--json] [stats|reset|doctor]", file=sys.stderr)
    return 2

"""``hermes skill-stats`` — bare call shows global; ``reset`` clears global."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import skill_stats_store as _store


def _add_display_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--day", "-d", type=int, default=_store.DEFAULT_DAYS,
                   help="Statistics period in days (default: 1); 0 = all time")
    p.add_argument("--offset", type=int, default=0, help="First row to show (default: 0)")
    p.add_argument("--limit", type=int, default=_store.DEFAULT_LIMIT,
                   help=f"Rows per page (default: {_store.DEFAULT_LIMIT})")
    p.add_argument("--group", "--group-by-category", dest="group", action="store_true",
                   help="Group statistics by skill category")


def setup_cli(parser: argparse.ArgumentParser) -> None:
    # Bare `hermes skill-stats` shows global stats (no subcommand needed).
    parser.add_argument("--scope", choices=["global", "session"], default="global",
                        help="Stats scope (default: global)")
    parser.add_argument("--session", default="", help="Session ID (required for --scope session)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    _add_display_args(parser)
    sub = parser.add_subparsers(dest="subcommand")
    sp = sub.add_parser("stats", help="Show skill usage statistics (bare call = global)")
    sp.add_argument("--scope", choices=["global", "session"], default="global")
    sp.add_argument("--session", default="", help="Session ID (required for --scope session)")
    sp.add_argument("--json", action="store_true")
    _add_display_args(sp)
    rp = sub.add_parser("reset", help="Reset global statistics")
    rp.add_argument("--scope", choices=["global", "session"], default="global")
    rp.add_argument("--session", default="", help="Session ID (required for session scope)")
    rp.add_argument("--yes", action="store_true", help="Confirm reset (no longer required; kept for compat)")
    dp = sub.add_parser("doctor", help="Plugin health check")
    dp.add_argument("--json", action="store_true")


def _print_stats(scope: str, session_id: str, as_json: bool, *, days: int,
                 offset: int, limit: int, group: bool) -> None:
    table = _store.get_table(scope, session_id=session_id, days=days)
    if group:
        table = _store.group_by_category(table)
    if as_json:
        table["offset"] = offset
        table["limit"] = limit
        table["group"] = group
        table["series"] = _store.get_series_all(days=max(days, 1), scope=scope, session_id=session_id)
        print(json.dumps(table, indent=2))
        return
    use_ansi = sys.stdout.isatty()  # bold headers only on a real terminal
    print(_store.format_table(table, group=group, offset=offset, limit=limit, use_ansi=use_ansi))


def handle_cli(args: Any) -> int:
    sub = getattr(args, "subcommand", None)
    if sub is None:
        # Bare `hermes skill-stats` = global stats.
        _print_stats(getattr(args, "scope", "global") or "global",
                     getattr(args, "session", "") or "", bool(getattr(args, "json", False)),
                     days=getattr(args, "day", _store.DEFAULT_DAYS),
                     offset=getattr(args, "offset", 0),
                     limit=getattr(args, "limit", _store.DEFAULT_LIMIT),
                     group=bool(getattr(args, "group", False)))
        return 0
    if sub == "stats":
        _print_stats(args.scope, args.session or "", bool(args.json),
                     days=args.day, offset=args.offset, limit=args.limit, group=args.group)
        return 0
    if sub == "reset":
        if args.scope == "session" and not args.session:
            print("skill-stats: --session is required for session scope", file=sys.stderr)
            return 2
        _store.reset_stats(args.scope, session_id=args.session or "")
        print(f"skill-stats: reset {args.scope} stats.")
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
    print("skill-stats: usage: hermes skill-stats [--scope global|session] [--day N] "
          "[--offset N] [--limit N] [--group] [stats|reset|doctor]", file=sys.stderr)
    return 2

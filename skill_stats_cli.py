"""``hermes skill-stats`` — bare call shows global; ``reset`` clears global."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import skill_stats_store as _store


def setup_cli(parser: argparse.ArgumentParser) -> None:
    # Bare `hermes skill-stats` shows global stats (no subcommand needed).
    parser.add_argument("--scope", choices=["global", "session"], default="global",
                        help="Stats scope (default: global)")
    parser.add_argument("--session", default="", help="Session ID (required for --scope session)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    sub = parser.add_subparsers(dest="subcommand")
    sp = sub.add_parser("stats", help="Show skill usage statistics (bare call = global)")
    sp.add_argument("--scope", choices=["global", "session"], default="global")
    sp.add_argument("--session", default="", help="Session ID (required for --scope session)")
    sp.add_argument("--json", action="store_true", help="Machine-readable output")
    rp = sub.add_parser("reset", help="Reset global statistics")
    rp.add_argument("--scope", choices=["global", "session"], default="global")
    rp.add_argument("--session", default="", help="Session ID (required for --scope session)")
    rp.add_argument("--yes", action="store_true", help="Confirm reset (no longer required; kept for compat)")
    dp = sub.add_parser("doctor", help="Plugin health check")
    dp.add_argument("--json", action="store_true", help="Machine-readable output")


def _print_stats(scope: str, session_id: str, as_json: bool) -> None:
    stats = _store.get_stats(scope, session_id=session_id)
    if as_json:
        stats["series"] = _store.get_series_all(scope=scope, session_id=session_id)
        print(json.dumps(stats, indent=2))
        return
    print(_store.format_stats(stats))


def handle_cli(args: Any) -> int:
    sub = getattr(args, "subcommand", None)
    if sub is None:
        # Bare `hermes skill-stats` = global stats.
        _print_stats(getattr(args, "scope", "global") or "global",
                     getattr(args, "session", "") or "", bool(getattr(args, "json", False)))
        return 0
    if sub == "stats":
        _print_stats(args.scope, args.session or "", bool(args.json))
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
            "plugin": {"name": "skill-stats", "version": "1.4.2"},
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
    print("skill-stats: usage: hermes skill-stats [--scope global|session] [stats|reset|doctor]", file=sys.stderr)
    return 2

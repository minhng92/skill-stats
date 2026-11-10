# Project Context

Hermes Agent plugin "skill-stats" (v0.9.0): per-skill usage counters with
period-scoped time-series charts. Standalone directory plugin — NO Hermes core
changes. Python is stdlib-only; the only extra dependency anywhere is
FastAPI (dashboard API tests). Requirements: Python >= 3.11.

## Architecture
- `__init__.py` — thin registration only: hooks (`pre_tool_call`,
  `on_session_start`, `on_session_end`), slash command `/skill-stats`,
  CLI `hermes skill-stats`, system-prompt section. All wiring goes through
  `register(ctx)`; no side effects at import time.
- `skill_stats_store.py` — JSON persistence + stats/series API. Storage:
  `$HERMES_HOME/skill-stats/global.json`, `sessions/<session_id>.json` and
  `pins.json` (dashboard pin list), atomic tmp-file replace, legacy
  `count`→`loads` migrated on read, events capped at 1000/skill. Also:
  `skill_categories()` (category from `<skills>/<category>/<skill>/SKILL.md`),
  `get_table()`/`group_by_category()`/`format_table()` (period-scoped display),
  `get_series(granularity=)` ("hour" for periods <= 3 days, else "day"),
  `get_pins/set_pins/toggle_pin`, `render_table` (ASCII, PrettyTable-style),
  `save_output`, `resolve_session_id` (exact id → id prefix → session title
  via Hermes' state.db, read-only), `VERSION`.
- `skill_stats_hooks.py` — counting (only `skill_view` counts; counting in
  `pre_tool_call`, so failed loads still count), the slash command, and
  `sync_tui_widget()` (register-time copy of the TUI widget into
  `$HERMES_HOME/tui-widgets/`, idempotent by size+mtime, never raises — this
  is the one sanctioned register-time side effect).
  Slash scope rule: `/skill-stats` shows the CURRENT session (host-injected
  `session_id`); `global` keyword = all-time; `--session/-s <id>` selects
  another session. CLI scope rule is different: bare call = global.
- `skill_stats_cli.py` — argparse CLI; bare call = global stats.
- `skill_stats_charts.py` — unicode text charts (bar + cumulative line).
- `dashboard/` — web tab: FastAPI `plugin_api.py` + React `src/` → `dist/`
  (esbuild bundle). See `dashboard/AGENTS.md`.
- `tui-widgets/` — plain Node ESM modal widget. See `tui-widgets/AGENTS.md`.
- `tests/` — pytest suite. See `tests/AGENTS.md`.
- `plugin.yaml` — plugin manifest; `package.json` — build tooling only;
  `pyproject.toml` — metadata for tooling/tests, NOT a build spec (Hermes
  loads the folder directly; relative imports only inside the package).

## Verify
- `python3 -m pytest -q` (repo root)
- `npm run check` — `node --check dashboard/dist/index.js`
- `npm run build` — rebuild `dashboard/dist/index.js` after editing
  `dashboard/src/index.jsx`

## Data semantics
- Env override for the data dir: `SKILL_STATS_DIR` (legacy
  `SKILL_ANALYTICS_DIR` still honored).
- Charts show recorded events only — never fabricate history (pre-v1.3
  counters legitimately have no events).
- Unknown/namespaced skill names (`superpowers:brainstorming`) are counted
  verbatim as given.
- Three surfaces must agree: terminal charts, Dashboard tab, TUI widget all
  render bar (daily) / line (cumulative) pairs for the same period; periods
  1d/3d bucket hourly, longer periods daily.
- Period options everywhere: 1, 3, 7, 30, 60, 90 days; default period 1 day;
  default page limit 10 (`PERIOD_OPTIONS`/`DEFAULT_DAYS`/`DEFAULT_LIMIT` in
  the store).
- Categories resolve at display time from the skills dir — never stored in
  the stats files (skills can move between categories).
- Plugin version lives in `plugin.yaml`, `package.json`,
  `dashboard/manifest.json`, `pyproject.toml` AND `skill_stats_store.VERSION`
  — update all five together. Version stays 0.x until the user calls the
  1.0.0 release.

## Conventions
- Stdlib-only Python, `from __future__ import annotations`, type hints.
- Never block tool calls: hooks return `None`; store failures log at debug
  and degrade to empty stats, never raise into the host.

## Do NOT
- Never import `dashboard/plugin_api.py` from the package — the host loads
  it via `spec_from_file_location` with no package; it loads the store by
  path itself.
- Never add a runtime dependency (stdlib-only is a hard rule) and never add
  a `[build-system]` section to `pyproject.toml`.
- Never write to the real `$HERMES_HOME` in tests — the conftest tmp
  fixture exists for this.
- Don't re-register hooks at runtime; registration happens once at startup,
  so plugin changes require a new Hermes session to take effect.
- Update `README.md` (user-facing command table) and `version` in BOTH
  `plugin.yaml` and `package.json` whenever behavior commands change —
  they ship 0.9.0 together (see Data semantics for the full version list).

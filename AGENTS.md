# Project Context

Hermes Agent plugin "skill-stats" (v1.4.2): per-skill usage counters with
daily time-series charts. Standalone directory plugin — NO Hermes core
changes. Python is stdlib-only; the only extra dependency anywhere is
FastAPI (dashboard API tests). Requirements: Python >= 3.11.

## Architecture
- `__init__.py` — thin registration only: hooks (`pre_tool_call`,
  `on_session_start`, `on_session_end`), slash command `/skill-stats`,
  CLI `hermes skill-stats`, system-prompt section. All wiring goes through
  `register(ctx)`; no side effects at import time.
- `skill_stats_store.py` — JSON persistence + stats/series API. Storage:
  `$HERMES_HOME/skill-stats/global.json` and `sessions/<session_id>.json`,
  atomic tmp-file replace, legacy `count`→`loads` migrated on read, events
  capped at 1000/skill.
- `skill_stats_hooks.py` — counting (only `skill_view` counts; counting in
  `pre_tool_call`, so failed loads still count) + the slash command.
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
  `SKILL_ANALYTICS_DIR` still honored as fallback).
- Charts show recorded events only — never fabricate history (pre-v1.3
  counters legitimately have no events).
- Unknown/namespaced skill names (`superpowers:brainstorming`) are counted
  verbatim as given.
- Three surfaces must agree: terminal charts, Dashboard tab, TUI widget all
  render the same bar (daily) / line (cumulative) pair.

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
  they ship version 1.4.2 together.

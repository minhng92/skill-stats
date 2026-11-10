# Skill Stats for Hermes Agent

Per-skill usage counters for Hermes Agent, with time-series daily buckets and
three chart surfaces: terminal text charts, a Dashboard tab, and an
interactive TUI widget.

Every `skill_view` load increments a counter **and** appends a timestamped
event. The event log (capped at 1000/skill) feeds daily bar and cumulative
line charts in all three surfaces.

> Plugin only, no Hermes core changes. Layout follows the official plugins:
> thin `__init__.py` (registration only), `skill_stats_store.py` (persistence
> + time series), `skill_stats_hooks.py` (counting + slash command),
> `skill_stats_cli.py` (CLI), `skill_stats_charts.py` (text charts),
> `dashboard/` (web tab), `tui-widgets/` (TUI modal).

## Install

Plugins are opt-in. Get a copy of this folder into your profile's plugins
directory, then enable:

```bash
# from a clone/download of this repo; HERMES_HOME defaults to ~/.hermes
mkdir -p "$HERMES_HOME/plugins"
cp -r skill-stats "$HERMES_HOME/plugins/"        # or: ln -s "$(pwd)/skill-stats" "$HERMES_HOME/plugins/skill-stats"
hermes plugins enable skill-stats
hermes plugins doctor skill-stats
```

For the interactive TUI widget, also copy the widget (per profile):

```bash
mkdir -p "$HERMES_HOME/tui-widgets"
cp "$HERMES_HOME/plugins/skill-stats/tui-widgets/skill-stats.mjs" "$HERMES_HOME/tui-widgets/"
```

Plugins are installed per profile: use `hermes -p <profile> plugins enable skill-stats`
for another profile (and copy the widget into that profile's `tui-widgets/`).
Restart Hermes (new session) after enabling — hooks register at startup; the
system-prompt pointer defers to the next session.

## Usage

All statistics views are **period-scoped** (default: last 1 day) with
`--offset/--limit` paging and an optional group-by-category mode.

| Surface | Command | What it shows / does |
|---|---|---|
| In-session | `/skill-stats` | **This session's** bordered table (skill, category, loads, %, last used) + top-skill bar/line charts |
| In-session | `/skill-stats --day 7` | Same, for the last 7 days |
| In-session | `/skill-stats global --offset 10 --limit 10` | Global stats, page 2 |
| In-session | `/skill-stats --group` | Grouped by skill category (loads, %, latest last-used) |
| In-session | `/skill-stats --json` | Table data + `series` per skill, machine-readable |
| In-session | `/skill-stats reset` | Reset **this session's** stats |
| TUI (`hermes --tui`) | `/skill-stats` | **Interactive modal** for the **current session**: ↑/↓ select skill, Enter opens chart, ←/→ toggles bar ↔ line, keys 1-7 switch period (1d 3d 7d 30d 60d 90d), Esc back/close |
| CLI | `hermes skill-stats` | **Global** table (bare call), period-scoped |
| CLI | `hermes skill-stats --day 30 -d 7 --offset 0 --limit 20 --group` | Period, paging, group-by-category |
| CLI | `hermes skill-stats --json` | Table data + `series`, machine-readable |
| CLI | `hermes skill-stats reset` | Reset **global** stats (+ all session files) |
| CLI | `hermes skill-stats doctor` | Plugin health check |
| Dashboard | `Skill Stats` tab (after Skills) | Table with Skill / Category / Loads / % / Last used / Chart / Pin columns; ← → paging, per-page dropdown (10-100), 1d-90d period buttons, group-by-category switcher, ★ pin/unpin (pinned skills stay on top) |

`hermes skill-stats stats [--scope session --session <ID>]` also works as an
explicit alias. Periods of 1 or 3 days render chart x-axes **hourly**; longer
periods are daily (TUI + Dashboard).

Note: in the TUI, the `/skill-stats` widget (interactive modal) takes
precedence over the plugin's text `/skill-stats`; everywhere else the plugin
command applies. The widget reads the **newest session file** under
`$HERMES_HOME/skill-stats/sessions/` (fallback: `global.json`) directly — no
backend needed.

## Data

```
$HERMES_HOME/skill-stats/global.json
$HERMES_HOME/skill-stats/sessions/<session_id>.json
$HERMES_HOME/skill-stats/pins.json          # dashboard pin list
```

Each stats file: `{"skills": {"<name>": {"loads": N, "last_used": <epoch>, "events": [<epoch>, ...]}}, "total_loads": N, "updated_at": <epoch>}`.
Override the data dir with `SKILL_STATS_DIR=/absolute/path` (legacy
`SKILL_ANALYTICS_DIR` still honored). Charts show recorded events only, never
fabricated history.

**Categories** come from the profile's skills directory layout:
`<skills>/<category>/<skill>/SKILL.md` → the skill belongs to `<category>`;
top-level `<skills>/<skill>/SKILL.md` → no category (blank). Plugin-provided
skills (namespaced names) have no category folder and show blank.

**Percentage** is the skill's share of loads within the selected period.

**Pins** (`pins.json`) order the Dashboard table: pinned skills stay on top
(sorted by loads among themselves) for easy monitoring.

## Stats output (0.9.0)

Terminal / slash / CLI all render the same bordered table (headers bolded on
a real TTY):

```
skill-stats — global · period: 1d
total loads (1d): 4 · unique skills: 3
+---------------+---------------------+-------+--------+------------------+
| SKILL         | CATEGORY            | LOADS | PCT    | LAST USED        |
+---------------+---------------------+-------+--------+------------------+
| hermes-agent  | autonomous-ai-agents|     2 | 50.00% | 2026-11-10 16:59 |
| ub-mode       | software-development|     1 | 25.00% | 2026-11-10 16:49 |
| superpowers:x |                     |     1 | 25.00% | 2026-11-10 16:40 |
+---------------+---------------------+-------+--------+------------------+
```

- `LOADS` — loads within the selected period (`--day`, default 1; `0` = all time).
- `PCT` — share of the period's total loads.
- `CATEGORY` — blank when the skill has no category folder.
- `--group` replaces the skill rows with per-category rows (loads, %, latest
  last-used). `--offset/--limit` page the rows (default `0`/`10`).

## What counts as a "use"

Only `skill_view` (loading a skill's instructions). `skills_list` (browsing) and
`skill_manage` (creating/editing skills) do not count. Counting happens before
execution, so a failed `skill_view` still counts as an attempted use. Unknown or
namespaced names (e.g. `superpowers:brainstorming`) are counted verbatim.

## Tests

```bash
python3 -m pytest -q
```

Stdlib-only (+ FastAPI for the dashboard API tests); no hermes-agent checkout
needed on `PYTHONPATH`. Widget logic is covered by `node --check` plus a
stub-SDK harness (see git history / issue notes).

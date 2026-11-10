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

Plugins are opt-in. Symlink/copy this folder into your profile's plugins dir,
then enable:

```bash
mkdir -p "$HERMES_HOME/plugins"
ln -s /data/kyzlab/plugins/skill-stats "$HERMES_HOME/plugins/skill-stats"
hermes plugins enable skill-stats
hermes plugins doctor skill-stats
```

For the interactive TUI widget, also copy the widget (per profile):

```bash
mkdir -p "$HERMES_HOME/tui-widgets"
cp /data/kyzlab/plugins/skill-stats/tui-widgets/skill-stats.mjs "$HERMES_HOME/tui-widgets/"
```

Plugins are installed per profile: use `hermes -p <profile> plugins enable skill-stats`
for another profile (and copy the widget into that profile's `tui-widgets/`).
Restart Hermes (new session) after enabling — hooks register at startup; the
system-prompt pointer defers to the next session.

## Usage

| Surface | Command | What it shows / does |
|---|---|---|
| In-session | `/skill-stats` | **This session's** table + top-skill 14d bar/cumulative charts |
| In-session | `/skill-stats global` | Global (all-time) table + charts |
| In-session | `/skill-stats --json` | Table data + `series` per skill, machine-readable |
| In-session | `/skill-stats reset` | Reset **this session's** stats |
| TUI (`hermes --tui`) | `/skill-stats` | **Interactive modal**: ↑/↓ select skill, Enter opens chart, ←/→ toggles bar (daily) ↔ line (cumulative), Esc back/close |
| CLI | `hermes skill-stats` | **Global** table (bare call) |
| CLI | `hermes skill-stats --json` | Global + `series`, machine-readable |
| CLI | `hermes skill-stats reset` | Reset **global** stats (+ all session files) |
| CLI | `hermes skill-stats doctor` | Plugin health check |
| Dashboard | `Skill Stats` tab (after Skills) | Table with per-skill counter + 📊 Chart button; chart view has ◀ Bar / Line ▶ toggle buttons and 7/30/90-day ranges |

`hermes skill-stats stats [--scope session --session <ID>]` also works as an explicit alias.

Note: in the TUI, the `/skill-stats` widget (interactive modal) takes
precedence over the plugin's text `/skill-stats`; everywhere else the plugin
command applies. The widget reads `$HERMES_HOME/skill-stats/global.json`
directly — no backend needed.

## Data

```
$HERMES_HOME/skill-stats/global.json
$HERMES_HOME/skill-stats/sessions/<session_id>.json
```

Each file: `{"skills": {"<name>": {"loads": N, "last_used": <epoch>, "events": [<epoch>, ...]}}, "total_loads": N, "updated_at": <epoch>}`.
Override the data dir with `SKILL_STATS_DIR=/absolute/path` (legacy `SKILL_ANALYTICS_DIR` still honored).
Pre-v1.2 counters have no events until new loads happen — charts show
recorded events only, never fabricated history.

## Stats output (v1.4.2)

Terminal / slash / CLI all render the same table:

```
skill-stats — global
total loads: 18 · unique skills: 6 · last stats: 2026-11-10 15:27
skill                                    loads  last_used
hermes-agent                                 5  2026-11-10 01:48
stageshow                                    5  2026-11-10 09:16
...
```

- `loads` — cumulative per-skill load counter.
- Header: `total loads: <sum> · unique skills: <distinct> · last stats: <YYYY-MM-DD> <HH:MM>`.

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

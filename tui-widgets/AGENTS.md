# tui-widgets/ — TUI modal widget

`skill-stats.mjs` — interactive modal for `hermes --tui`, shown on
`/skill-stats` in the TUI (takes precedence over the plugin's text slash
command there).

## Rules
- Single plain Node ESM file, `node:` imports only (fs/os/path). No npm
  deps, no build step, not imported by the Python package.
- Auto-installed: `skill_stats_hooks.sync_tui_widget()` (called from
  `register()`) copies this file to `$HERMES_HOME/tui-widgets/` on every
  Hermes start; skip when size+mtime match, never raise into the host. Edit
  here, and the next session (or `/widgets-reload`) picks it up — no manual
  copy step.
- Data: read the **newest** file in `$HERMES_HOME/skill-stats/sessions/`
  (the current session; fallback `global.json`) — `HERMES_HOME` env, fallback
  `~/.hermes` — no network, no backend.
- UI contract: `defineWidgetApp` with `id: 'skill-stats'`, `mode: 'modal'`,
  `init()/reduce()/render()`; keys: ↑/↓ (and j/k) select, Enter/Space opens
  chart, ←/→ (h/l) toggle bar↔line, 1-6 switch period (1d 3d 7d 30d 60d 90d;
  default 1d; the old key "7" binding was removed as redundant), Esc/q
  back/close. Keep the help string in sync with any key change.
- Table columns: name / category (from `<skills>/<category>/<skill>/SKILL.md`,
  blank when none) / loads (period) / pct / sparkline. Chart x-axis is hourly
  for 1d/3d periods, daily beyond (with an axis label line).
- reduce() must return the SAME state object when nothing changes (period key
  for the current period, no-op keys) — a fresh object on every key event
  re-renders and can clear the chat screen behind the modal.
- Render with the host theme (`t.color.primary/label/muted/text`) and
  `sparkRows` for charts — no ANSI color codes of our own.
- Chart semantics must match the other surfaces: bar (bucketed per period —
  hourly for 1d/3d, daily beyond) and cumulative line (see root AGENTS.md
  "Data semantics").
- Verify with `node --check tui-widgets/skill-stats.mjs` after edits.

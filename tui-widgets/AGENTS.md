# tui-widgets/ — TUI modal widget

`skill-stats.mjs` — interactive modal for `hermes --tui`, shown on
`/skill-stats` in the TUI (takes precedence over the plugin's text slash
command there).

## Rules
- Single plain Node ESM file, `node:` imports only (fs/os/path). No npm
  deps, no build step, not imported by the Python package.
- Not auto-installed: users copy it to `$HERMES_HOME/tui-widgets/` (see
  README Install), then `/widgets-reload`. It runs in the TUI widget host.
- Data: read `$HERMES_HOME/skill-stats/global.json` directly
  (`HERMES_HOME` env, fallback `~/.hermes`) — no network, no backend, no
  session scope (global only by design).
- UI contract: `defineWidgetApp` with `id: 'skill-stats'`, `mode: 'modal'`,
  `init()/reduce()/render()`; keys: ↑/↓ (and j/k) select, Enter/Space opens
  chart, ←/→ (h/l) toggle bar↔line, Esc/q back/close. Keep the help string
  in sync with any key change.
- Render with the host theme (`t.color.primary/label/muted/text`) and
  `sparkRows` for charts — no ANSI color codes of our own.
- Chart semantics must match the other surfaces: 30-day daily buckets and
  cumulative (see root AGENTS.md "Data semantics").
- Verify with `node --check tui-widgets/skill-stats.mjs` after edits.

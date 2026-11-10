# dashboard/ — web tab

Skill Stats dashboard plugin: a Hermes web-dashboard tab (React bundle) +
read-only FastAPI backend.

## Layout
- `manifest.json` — tab config (`/skill-stats`, position `after:skills`,
  entry `dist/index.js`, api `plugin_api.py`). Version here must match the
  root `plugin.yaml` / `package.json`.
- `plugin_api.py` — FastAPI router mounted by the host at
  `/api/plugins/skill-stats/`. Routes: `GET /overview?days=`,
  `GET /skills/{name}?days=&scope=&session_id=`, `GET /session?session_id=`.
- `src/index.jsx` — the only UI source. Compiled IIFE bundle.
- `dist/index.js` — committed build artifact; the host serves THIS file,
  not `src/`.

## Rules
- After editing `src/index.jsx`, ALWAYS run `npm run build` (repo root) so
  `dist/index.js` ships the change, then `npm run check` to syntax-verify
  the bundle. Never hand-edit `dist/index.js`.
- React comes from the host SDK, NOT npm: `window.__HERMES_PLUGIN_SDK__`
  (React, hooks, components, cn, fetchJSON) and JSX factory
  `React.createElement` via `h = React.createElement`. Don't add React or
  any UI lib to package.json — esbuild is the only devDependency.
- `plugin_api.py` is loaded by the host via `spec_from_file_location` with
  no package, so relative imports are unavailable — it loads
  `skill_stats_store.py` from the parent dir by path (`_store()`). Keep
  that pattern; don't convert to `from .. import`.
- Backend is read-only against `$HERMES_HOME/skill-stats/` and clamps
  `days` to 1..90; the UI's 7/30/90-day buttons stay within that.
- Routing is hash-based (`/skill-stats#/skills/<name>`) via
  `window.location.hash` — no router library.
- Theme: use SDK components (`Card`, `Badge`, `Button`) and `cn` classes
  (`text-text-secondary`, etc.) — host supplies Tailwind tokens; don't
  inline color hex values.

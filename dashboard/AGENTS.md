# dashboard/ — web tab

Skill Stats dashboard plugin: a Hermes web-dashboard tab (React bundle) +
read-only FastAPI backend.

## Layout
- `manifest.json` — tab config (`/skill-stats`, position `after:skills`,
  entry `dist/index.js`, api `plugin_api.py`). Version here must match the
  root `plugin.yaml` / `package.json`.
- `plugin_api.py` — FastAPI router mounted by the host at
  `/api/plugins/skill-stats/`. Routes: `GET /overview?days=&profile=`
  (period-scoped rows: skill/category/loads/pct/last_used + all-time totals +
  pins + series), `GET /skills/{name}?days=&granularity=` (hourly buckets for
  days <= 3, daily beyond; auto unless `granularity=hour|day` given),
  `GET/POST /pins` (pin list; POST body `{"skill", "pinned?"}` — omit
  `pinned` to toggle), `GET /session?session_id=` (session_id resolves via
  the store: exact id, id prefix, or session title).
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
- The host appends `&profile=<name>` to plugin API requests. Honor it:
  `default`/empty → the server's `$HERMES_HOME/skill-stats`; any other
  profile → `$HERMES_HOME/profiles/<name>/skill-stats` (via
  `_profile_data_dir`, which rejects unsafe names by falling back to
  default). Never ignore the param — that shows the wrong profile's data.
- Frontend must read numeric series/counter values with a
  `r.loads ?? r.count` fallback (the `val` helper in `Chart`) — a
  long-running dashboard server may still serve the legacy `count` field
  name; reading `r.loads` alone renders `NaN` geometry and a blank chart.
- Backend clamps `days` to 1..90 (period options 1/3/7/30/60/90 in the UI,
  default 1d); only `/pins` writes (pins.json) — everything else is
  read-only against `$HERMES_HOME/skill-stats/`.
- Table UI: Skill / Category / Loads / % / Last used / Chart / Pin columns;
  pinned skills (★) sort first; ← → paging with a per-page dropdown
  (10/15/20/30/50/100, default 10) and a "Group by" radiogroup
  (Skill | Category). Period selection is a radiogroup (1d-90d); the chart
  view has a Bar/Line radiogroup.
- Radiogroups are built on the host Tabs kit — its standard segmented
  control. Exact contract: `Tabs` takes `defaultValue` and a RENDER-FUNCTION
  child `(value, setValue) => ...` (a plain element crashes with
  "e is not a function"); `TabsTrigger` takes an `active` BOOLEAN (not
  radix state); `TabsList` is a passthrough div (put `role="radiogroup"` +
  `aria-label` there, `role="radio"` + `aria-checked` on triggers). See the
  `RadioGroup` helper in `src/index.jsx`.
- Routing is hash-based (`/skill-stats#/skills/<name>`) via
  `window.location.hash` — no router library.
- Theme: use SDK components (`Card`, `Badge`, `Button`) and `cn` classes
  (`text-text-secondary`, etc.) — host supplies Tailwind tokens; don't
  inline color hex values.

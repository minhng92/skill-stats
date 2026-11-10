/**
 * Skill Stats — Hermes Agent dashboard plugin (source).
 *
 * Compiled to dashboard/dist/index.js by `npm run build` (esbuild, IIFE, React
 * external via window.__HERMES_PLUGIN_SDK__).
 *
 * Views (hash-routed):
 *   /skill-stats                       table: category/%/pin columns, paging,
 *                                      period 1d-90d, group-by-category switcher
 *   /skill-stats#/skills/<name>        chart: bar / cumulative line; hourly
 *                                      x-axis for 1d/3d, daily beyond
 *
 * Data: GET /api/plugins/skill-stats/* (plugin_api.py); pin toggles POST to
 * /pins. Periods <= 3 days are bucketed hourly by the backend.
 */

const SDK = window.__HERMES_PLUGIN_SDK__;
const { React } = SDK;
const { useState, useEffect, useCallback } = SDK.hooks;
const { Card, CardHeader, CardTitle, CardContent, Badge, Button, Tabs, TabsList, TabsTrigger } = SDK.components;
const { cn } = SDK.utils;
const h = React.createElement;

const PLUGIN_NAME = "skill-stats";
const API = "/api/plugins/skill-stats";
const PERIODS = [1, 3, 7, 30, 60, 90];
const LIMITS = [10, 15, 20, 30, 50, 100];

// ─── helpers ────────────────────────────────────────────────────────────────

function formatDate(iso) {
  try {
    return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

// Bucket label → axis text. Hourly buckets are "YYYY-MM-DDTHH:00".
function formatBucket(iso) {
  if (typeof iso === "string" && iso.includes("T")) {
    const [d, hm] = iso.split("T");
    return `${d.slice(5)} ${hm.slice(0, 5)}`;
  }
  return formatDate(iso);
}

function formatTime(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function fmtPct(p) {
  return `${Number(p ?? 0).toFixed(2)}%`;
}

function parseHash(hash) {
  const m = /^#\/skills\/([^/?#]+)/.exec(hash || "");
  return m ? { view: "chart", skill: decodeURIComponent(m[1]) } : { view: "table" };
}

function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function openChart(skill) {
  window.location.hash = `/skills/${encodeURIComponent(skill)}`;
}

function backToTable() {
  window.location.hash = "";
}

async function postJSON(url, body) {
  // Forward the webapp's selected profile (location.search) so per-profile
  // backends write to the right data dir — GET fetches get this from the
  // SDK's fetchJSON, but our raw POST must add it itself.
  const profile = new URLSearchParams(window.location.search).get("profile");
  if (profile && !url.includes("profile=")) {
    url += (url.includes("?") ? "&" : "?") + "profile=" + encodeURIComponent(profile);
  }
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${url} -> ${res.status}`);
  return res.json();
}

// ─── SVG chart ──────────────────────────────────────────────────────────────

function Chart({ series, kind, width = 720, height = 260 }) {
  if (!series || series.length === 0) {
    return h("p", { className: "text-sm text-text-secondary" }, "No recorded events in this window yet (charts start with the first counted load).");
  }
  // Accept both the v1.3+ `loads` key and the legacy `count` key so charts
  // render even while a long-running dashboard server still serves the old
  // store field names.
  const val = (r) => Number((r && (r.loads ?? r.count)) ?? 0) || 0;
  const max = Math.max(1, ...series.map(val));
  const padL = 44, padR = 12, padT = 14, padB = 28;
  const iw = width - padL - padR, ih = height - padT - padB;
  const x = (i) => padL + (series.length === 1 ? iw / 2 : (iw * i) / (series.length - 1));
  const y = (v) => padT + ih - (ih * v) / max;
  const bw = Math.max(2, Math.min(18, (iw / series.length) * 0.6));
  const ticks = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);
  const line = series.map((r, i) => `${x(i)},${y(val(r))}`).join(" ");
  return h(
    "svg",
    { viewBox: `0 0 ${width} ${height}`, width: "100%", role: "img", "aria-label": `${kind} chart` },
    ticks.map((v) =>
      h("g", { key: `t${v}` },
        h("line", { x1: padL, x2: width - padR, y1: y(v), y2: y(v), stroke: "currentColor", strokeOpacity: 0.15 }),
        h("text", { x: padL - 6, y: y(v) + 4, textAnchor: "end", fontSize: 11, fill: "currentColor", opacity: 0.7 }, String(v))
      )
    ),
    kind === "bar"
      ? series.map((r, i) => h("rect", {
          key: r.date, x: x(i) - bw / 2, y: y(val(r)), width: bw, height: Math.max(0, ih - (y(val(r)) - padT)),
          rx: 2, fill: "currentColor", opacity: val(r) ? 0.85 : 0.15,
        }))
      : [
          h("polygon", { key: "area", points: `${x(0)},${y(0)} ${line} ${x(series.length - 1)},${y(0)}`, fill: "currentColor", opacity: 0.15 }),
          h("polyline", { key: "line", points: line, fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinejoin: "round" }),
        ],
    [0, Math.floor((series.length - 1) / 2), series.length - 1].map((i) =>
      h("text", { key: `x${i}`, x: x(i), y: height - 8, textAnchor: "middle", fontSize: 11, fill: "currentColor", opacity: 0.7 },
        formatBucket(series[i].date))
    )
  );
}

// ─── table helpers ──────────────────────────────────────────────────────────

function sortRows(skills, pins) {
  const pinned = new Set(pins || []);
  return [...skills].sort((a, b) => {
    const pa = pinned.has(a.skill) ? 0 : 1, pb = pinned.has(b.skill) ? 0 : 1;
    if (pa !== pb) return pa - pb; // pinned block first
    if (b.loads !== a.loads) return b.loads - a.loads;
    return String(a.skill).localeCompare(String(b.skill));
  });
}

function groupRows(skills) {
  const agg = new Map();
  let total = 0;
  for (const s of skills) {
    const key = s.category || "(uncategorized)";
    const a = agg.get(key) || { category: key, loads: 0, last_used: 0 };
    a.loads += Number(s.loads ?? s.count ?? 0);
    a.last_used = Math.max(a.last_used, Number(s.last_used ?? 0));
    agg.set(key, a);
    total += Number(s.loads ?? s.count ?? 0);
  }
  const rows = [...agg.values()].map((a) => ({ ...a, pct: total ? (a.loads * 100) / total : 0 }));
  rows.sort((a, b) => b.loads - a.loads || a.category.localeCompare(b.category));
  return rows;
}

// Single-choice selector on the host's Tabs kit (its standard segmented
// control): Tabs takes defaultValue + a (value, setValue) render function;
// TabsTrigger takes an `active` boolean. Wrapped as a radiogroup for a11y.
function RadioGroup({ value, onChange, options, label }) {
  return h(Tabs, { defaultValue: value }, (val, setVal) =>
    h(TabsList, { role: "radiogroup", "aria-label": label },
      options.map((o) =>
        h(TabsTrigger, {
          key: o.value, value: o.value, active: o.value === val,
          role: "radio", "aria-checked": o.value === val, "aria-label": o.label,
          onClick: () => { setVal(o.value); onChange(o.value); },
        }, o.label))));
}

function PeriodSelect({ days, setDays }) {
  return RadioGroup({
    value: String(days),
    onChange: (v) => setDays(Number(v)),
    label: "Statistics period",
    options: PERIODS.map((d) => ({ value: String(d), label: `${d}d` })),
  });
}

// ─── views ──────────────────────────────────────────────────────────────────

function TableView({ data, days, setDays, refresh, limit, setLimit, page, setPage, group, setGroup, onPin }) {
  const skills = data?.skills ?? [];
  const pins = data?.pins ?? [];
  const rows = group ? groupRows(skills) : sortRows(skills, pins);
  const pageCount = Math.max(1, Math.ceil(rows.length / limit));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = rows.slice(safePage * limit, safePage * limit + limit);
  const pinnedSet = new Set(pins);

  const headers = group
    ? ["Category", "Loads", "%", "Last used"]
    : ["Skill", "Category", "Loads", "%", "Last used", "Chart", "Pin"];

  return h(Card, null,
    h(CardHeader, null,
      h(CardTitle, null, `Skill usage${group ? " — by category" : ""} (last ${days}d)`),
      h("p", { className: "text-sm text-text-secondary" },
        data ? `loads (${days}d): ${data.period_loads ?? 0} · total loads: ${data.total_loads ?? 0} · unique skills: ${data.unique_skills ?? 0}` : ""),
      h("div", { className: "flex flex-wrap items-center gap-2" },
        PeriodSelect({ days, setDays }),
        RadioGroup({
          value: group ? "category" : "skill",
          onChange: (v) => { setGroup(v === "category"); setPage(0); },
          label: "Group by skill or category",
          options: [{ value: "skill", label: "Skill" }, { value: "category", label: "Category" }],
        }),
        h("span", { className: "mx-1" }),
        h("label", { className: "text-sm text-text-secondary" }, "Per page "),
        h("select", {
          value: String(limit),
          onChange: (e) => { setLimit(Number(e.target.value)); setPage(0); },
          className: "bg-transparent border border-current/20 rounded px-1 py-0.5 text-sm",
          "aria-label": "Rows per page",
        }, LIMITS.map((n) => h("option", { key: n, value: String(n) }, String(n)))),
        h(Button, { size: "sm", variant: "outline", disabled: safePage <= 0, onClick: () => setPage(safePage - 1), "aria-label": "Previous page" }, "←"),
        h("span", { className: "text-sm text-text-secondary" }, `page ${safePage + 1}/${pageCount}`),
        h(Button, { size: "sm", variant: "outline", disabled: safePage >= pageCount - 1, onClick: () => setPage(safePage + 1), "aria-label": "Next page" }, "→"),
        h(Button, { size: "sm", variant: "outline", onClick: refresh }, "Refresh")
      )
    ),
    h(CardContent, null,
      !data ? h("p", { className: "text-sm" }, "Loading…") :
      rows.length === 0 ? h("p", { className: "text-sm text-text-secondary" }, "No skill loads recorded in this period — load a skill in chat, then come back.") :
      h("table", { className: "w-full text-sm" },
        h("thead", null, h("tr", { className: "text-left text-text-secondary" },
          headers.map((c) => h("th", { key: c, className: "py-2 pr-4 font-medium" }, c)))),
        h("tbody", null,
          pageRows.map((s) => group
            ? h("tr", { key: s.category, className: "border-t border-current/10" },
                h("td", { className: "py-2 pr-4 font-medium" }, s.category),
                h("td", { className: "py-2 pr-4" }, h(Badge, null, String(s.loads ?? 0))),
                h("td", { className: "py-2 pr-4" }, fmtPct(s.pct)),
                h("td", { className: "py-2 pr-4 text-text-secondary" }, formatTime(s.last_used)))
            : h("tr", { key: s.skill, className: "border-t border-current/10" },
                h("td", { className: "py-2 pr-4 font-medium" },
                  pinnedSet.has(s.skill) ? "★ " : "", s.skill),
                h("td", { className: "py-2 pr-4 text-text-secondary" }, s.category || ""),
                h("td", { className: "py-2 pr-4" }, h(Badge, null, String(s.loads ?? s.count ?? 0))),
                h("td", { className: "py-2 pr-4" }, fmtPct(s.pct)),
                h("td", { className: "py-2 pr-4 text-text-secondary" }, formatTime(s.last_used)),
                h("td", { className: "py-2 pr-4" },
                  h(Button, { size: "sm", variant: "outline", "aria-label": `Chart for ${s.skill}`, onClick: () => openChart(s.skill) }, "📊 Chart")),
                h("td", { className: "py-2" },
                  h(Button, {
                    size: "sm", variant: "outline",
                    "aria-label": pinnedSet.has(s.skill) ? `Unpin ${s.skill}` : `Pin ${s.skill}`,
                    onClick: () => onPin(s.skill, !pinnedSet.has(s.skill)),
                  }, pinnedSet.has(s.skill) ? "★ Unpin" : "☆ Pin"))
              ))
        )
      )
    )
  );
}

function ChartView({ skill, days, setDays }) {
  const [detail, setDetail] = useState(null);
  const [kind, setKind] = useState("bar");
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setError(null);
    SDK.fetchJSON(`${API}/skills/${encodeURIComponent(skill)}?days=${days}`)
      .then(setDetail)
      .catch((e) => setError(String(e)));
  }, [skill, days]);

  useEffect(() => { load(); }, [load]);

  const series = detail ? (kind === "line" ? detail.cumulative : detail.series) : null;
  const gran = detail?.granularity === "hour" ? "hourly x-axis" : "daily x-axis";
  return h(Card, null,
    h(CardHeader, null,
      h(CardTitle, null, detail ? `${detail.skill} — ${detail.period_loads ?? detail.loads ?? 0} loads (${days}d)` : "Skill chart"),
      h("div", { className: "flex flex-wrap items-center gap-2" },
        h(Button, { size: "sm", variant: "outline", onClick: backToTable }, "← Back"),
        PeriodSelect({ days, setDays }),
        RadioGroup({
          value: kind,
          onChange: setKind,
          label: "Chart type",
          options: [{ value: "bar", label: "Bar" }, { value: "line", label: "Line" }],
        }),
        h(Badge, null, kind === "line" ? "cumulative" : "daily"),
        h(Badge, null, gran)
      )
    ),
    h(CardContent, null,
      error ? h("p", { className: "text-sm", role: "alert" }, error) :
      !detail ? h("p", { className: "text-sm" }, "Loading…") :
      h(Chart, { series, kind })
    )
  );
}

function SkillStatsPage() {
  const route = useHashRoute();
  const [data, setData] = useState(null);
  const [days, setDays] = useState(1);
  const [limit, setLimit] = useState(10);
  const [page, setPage] = useState(0);
  const [group, setGroup] = useState(false);

  const refresh = useCallback(() => {
    SDK.fetchJSON(`${API}/overview?days=${days}`).then(setData).catch(() => setData(null));
  }, [days]);

  useEffect(() => { refresh(); }, [refresh]);

  const onPin = useCallback(async (skill, pinned) => {
    try {
      const res = await postJSON(`${API}/pins`, { skill, pinned });
      setData((d) => (d ? { ...d, pins: res.pins } : d));
    } catch { refresh(); }
  }, [refresh]);

  return h("div", { className: "max-w-5xl p-4" },
    route.view === "chart"
      ? h(ChartView, { skill: route.skill, days, setDays })
      : h(TableView, { data, days, setDays, refresh, limit, setLimit, page, setPage, group, setGroup, onPin }));
}

window.__HERMES_PLUGINS__.register(PLUGIN_NAME, SkillStatsPage);

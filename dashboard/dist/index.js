(() => {
  // dashboard/src/index.jsx
  var SDK = window.__HERMES_PLUGIN_SDK__;
  var { React } = SDK;
  var { useState, useEffect, useCallback } = SDK.hooks;
  var { Card, CardHeader, CardTitle, CardContent, Badge, Button } = SDK.components;
  var { cn } = SDK.utils;
  var h = React.createElement;
  var PLUGIN_NAME = "skill-stats";
  var API = "/api/plugins/skill-stats";
  function formatDate(iso) {
    try {
      return (/* @__PURE__ */ new Date(`${iso}T00:00:00`)).toLocaleDateString(void 0, { month: "short", day: "numeric" });
    } catch {
      return iso;
    }
  }
  function formatTime(ts) {
    if (!ts) return "\u2014";
    return new Date(ts * 1e3).toLocaleString(void 0, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
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
  function Chart({ series, kind, width = 720, height = 260 }) {
    if (!series || series.length === 0) {
      return h("p", { className: "text-sm text-text-secondary" }, "No recorded events in this window yet (charts start with the first counted load).");
    }
    const max = Math.max(1, ...series.map((r) => r.loads));
    const padL = 44, padR = 12, padT = 14, padB = 28;
    const iw = width - padL - padR, ih = height - padT - padB;
    const x = (i) => padL + (series.length === 1 ? iw / 2 : iw * i / (series.length - 1));
    const y = (v) => padT + ih - ih * v / max;
    const bw = Math.max(2, Math.min(18, iw / series.length * 0.6));
    const ticks = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);
    const line = series.map((r, i) => `${x(i)},${y(r.loads)}`).join(" ");
    return h(
      "svg",
      { viewBox: `0 0 ${width} ${height}`, width: "100%", role: "img", "aria-label": `${kind} chart` },
      ticks.map(
        (v) => h(
          "g",
          { key: `t${v}` },
          h("line", { x1: padL, x2: width - padR, y1: y(v), y2: y(v), stroke: "currentColor", strokeOpacity: 0.15 }),
          h("text", { x: padL - 6, y: y(v) + 4, textAnchor: "end", fontSize: 11, fill: "currentColor", opacity: 0.7 }, String(v))
        )
      ),
      kind === "bar" ? series.map((r, i) => h("rect", {
        key: r.date,
        x: x(i) - bw / 2,
        y: y(r.loads),
        width: bw,
        height: Math.max(0, ih - (y(r.loads) - padT)),
        rx: 2,
        fill: "currentColor",
        opacity: r.loads ? 0.85 : 0.15
      })) : [
        h("polygon", { key: "area", points: `${x(0)},${y(0)} ${line} ${x(series.length - 1)},${y(0)}`, fill: "currentColor", opacity: 0.15 }),
        h("polyline", { key: "line", points: line, fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinejoin: "round" })
      ],
      [0, Math.floor((series.length - 1) / 2), series.length - 1].map(
        (i) => h(
          "text",
          { key: `x${i}`, x: x(i), y: height - 8, textAnchor: "middle", fontSize: 11, fill: "currentColor", opacity: 0.7 },
          formatDate(series[i].date)
        )
      )
    );
  }
  function TableView({ data, days, setDays, refresh }) {
    const skills = data?.skills ?? [];
    return h(
      Card,
      null,
      h(
        CardHeader,
        null,
        h(CardTitle, null, `Skill usage \u2014 global (last ${days} days)`),
        h("p", { className: "text-sm text-text-secondary" }, data ? `total loads: ${data.total_loads} \xB7 unique skills: ${data.unique_skills}` : ""),
        h(
          "div",
          { className: "flex items-center gap-2" },
          [7, 30, 90].map(
            (d) => h(Button, { key: d, size: "sm", variant: days === d ? "default" : "outline", onClick: () => setDays(d) }, `${d}d`)
          ),
          h(Button, { size: "sm", variant: "outline", onClick: refresh }, "Refresh")
        )
      ),
      h(
        CardContent,
        null,
        !data ? h("p", { className: "text-sm" }, "Loading\u2026") : skills.length === 0 ? h("p", { className: "text-sm text-text-secondary" }, "No skill loads recorded yet \u2014 load a skill in chat, then come back.") : h(
          "table",
          { className: "w-full text-sm" },
          h("thead", null, h(
            "tr",
            { className: "text-left text-text-secondary" },
            ["Skill", "Loads", "Last used", "Chart"].map((c) => h("th", { key: c, className: "py-2 pr-4 font-medium" }, c))
          )),
          h(
            "tbody",
            null,
            skills.map((s) => h(
              "tr",
              { key: s.skill, className: "border-t border-current/10" },
              h("td", { className: "py-2 pr-4 font-medium" }, s.skill),
              h("td", { className: "py-2 pr-4" }, h(Badge, null, String(s.loads ?? s.count ?? 0))),
              h("td", { className: "py-2 pr-4 text-text-secondary" }, formatTime(s.last_used)),
              h(
                "td",
                { className: "py-2" },
                h(Button, { size: "sm", variant: "outline", "aria-label": `Chart for ${s.skill}`, onClick: () => openChart(s.skill) }, "\u{1F4CA} Chart")
              )
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
      SDK.fetchJSON(`${API}/skills/${encodeURIComponent(skill)}?days=${days}`).then(setDetail).catch((e) => setError(String(e)));
    }, [skill, days]);
    useEffect(() => {
      load();
    }, [load]);
    const series = detail ? kind === "line" ? detail.cumulative : detail.series : null;
    return h(
      Card,
      null,
      h(
        CardHeader,
        null,
        h(CardTitle, null, detail ? `${detail.skill} \u2014 ${detail.loads ?? detail.count ?? 0} loads` : `Skill chart`),
        h(
          "div",
          { className: "flex items-center gap-2" },
          h(Button, { size: "sm", variant: "outline", onClick: backToTable }, "\u2190 Back"),
          [7, 30, 90].map(
            (d) => h(Button, { key: d, size: "sm", variant: days === d ? "default" : "outline", onClick: () => setDays(d) }, `${d}d`)
          ),
          h("span", { className: "mx-1" }),
          h(Button, { size: "sm", variant: kind === "bar" ? "default" : "outline", "aria-label": "Bar chart", onClick: () => setKind("bar") }, "\u25C0 Bar"),
          h(Button, { size: "sm", variant: kind === "line" ? "default" : "outline", "aria-label": "Cumulative line chart", onClick: () => setKind("line") }, "Line \u25B6"),
          h(Badge, null, kind === "line" ? "cumulative" : "daily")
        )
      ),
      h(
        CardContent,
        null,
        error ? h("p", { className: "text-sm", role: "alert" }, error) : !detail ? h("p", { className: "text-sm" }, "Loading\u2026") : h(Chart, { series, kind })
      )
    );
  }
  function SkillStatsPage() {
    const route = useHashRoute();
    const [data, setData] = useState(null);
    const [days, setDays] = useState(30);
    const refresh = useCallback(() => {
      SDK.fetchJSON(`${API}/overview?days=${days}`).then(setData).catch(() => setData(null));
    }, [days]);
    useEffect(() => {
      refresh();
    }, [refresh]);
    return h(
      "div",
      { className: "max-w-5xl p-4" },
      route.view === "chart" ? h(ChartView, { skill: route.skill, days, setDays }) : h(TableView, { data, days, setDays, refresh })
    );
  }
  window.__HERMES_PLUGINS__.register(PLUGIN_NAME, SkillStatsPage);
})();

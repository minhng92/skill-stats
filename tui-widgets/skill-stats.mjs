/**
 * skill-stats — interactive skill usage viewer for the Hermes TUI.
 *
 * Copy to $HERMES_HOME/tui-widgets/skill-stats.mjs (see README), then
 * `/widgets-reload` and `/skill-stats`.
 *
 * Modal flow:
 *   table: Up/Down select a skill, Enter opens its chart, 1-6 switch the
 *          period (1d 3d 7d 30d 60d 90d), Esc/q closes
 *   chart: Left/Right toggles bar <-> line (cumulative), Up/Down switches
 *          skill, 1-6 switch period, Esc back to table
 *
 * Data: the CURRENT session's stats — newest file in
 * $HERMES_HOME/skill-stats/sessions/ (fallback: global.json). Written by the
 * skill-stats plugin; no network, no backend. Periods <= 3 days bucket the
 * chart HOURLY, longer periods daily.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const PERIODS = [1, 3, 7, 30, 60, 90]; // shortcut keys 1..6
const DEFAULT_PERIOD_IDX = 0; // 1d
const TABLE_LIMIT = 10;

function dataHome() {
  return process.env.HERMES_HOME || path.join(os.homedir(), '.hermes');
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

function loadScopeStats() {
  // Current (most recently written) session file; fallback to global.
  const base = path.join(dataHome(), 'skill-stats');
  const sessionsDir = path.join(base, 'sessions');
  let best = null, bestM = -1;
  try {
    for (const f of fs.readdirSync(sessionsDir)) {
      if (!f.endsWith('.json')) continue;
      const p = path.join(sessionsDir, f);
      const m = fs.statSync(p).mtimeMs;
      if (m > bestM) { bestM = m; best = p; }
    }
  } catch { /* no sessions dir yet */ }
  const doc = (best && readJson(best)) || readJson(path.join(base, 'global.json')) || { skills: {} };
  return { doc, scope: best ? 'session' : 'global', sessionFile: best ? path.basename(best, '.json') : '' };
}

function loadCategories() {
  // <skills>/<category>/<skill>/SKILL.md -> category; <skills>/<skill>/SKILL.md -> ''
  const base = path.join(dataHome(), 'skills');
  const out = {};
  let entries = [];
  try { entries = fs.readdirSync(base); } catch { return out; }
  for (const e of entries) {
    if (e.startsWith('.')) continue;
    const p = path.join(base, e);
    let st; try { st = fs.statSync(p); } catch { continue; }
    if (!st.isDirectory()) continue;
    if (fs.existsSync(path.join(p, 'SKILL.md'))) { out[e] = ''; continue; }
    let subs = [];
    try { subs = fs.readdirSync(p); } catch { continue; }
    for (const s of subs) {
      if (s.startsWith('.')) continue;
      if (fs.existsSync(path.join(p, s, 'SKILL.md'))) out[s] = e;
    }
  }
  return out;
}

function buildRows(doc, cats, days) {
  const since = Date.now() / 1000 - days * 86400;
  const rows = [];
  let total = 0;
  for (const [name, v] of Object.entries(doc.skills || {})) {
    const events = (v && Array.isArray(v.events)) ? v.events.map(Number) : [];
    const inWin = events.filter((ts) => ts >= since);
    const loads = days > 0 ? inWin.length : Number((v && v.loads) || 0);
    if (loads === 0) continue;
    total += loads;
    rows.push({
      name,
      category: cats[name] || '',
      loads,
      lastUsed: inWin.length ? Math.max(...inWin) : Number((v && v.last_used) || 0),
      events: inWin,
    });
  }
  rows.sort((a, b) => b.loads - a.loads || a.name.localeCompare(b.name));
  for (const r of rows) r.pct = total ? (r.loads * 100 / total) : 0;
  return { rows, total };
}

function dayLabel(ts) {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function hourLabel(ts) {
  const d = new Date(ts * 1000);
  return `${dayLabel(ts)}T${String(d.getHours()).padStart(2, '0')}:00`;
}

function bucketize(events, days) {
  // Periods <= 3 days bucket hourly; longer periods daily.
  const hourly = days <= 3;
  const step = hourly ? 3600 : 86400;
  const n = hourly ? days * 24 : days;
  const end = hourly
    ? Math.floor(Date.now() / 1000 / 3600) * 3600
    : (() => { const d = new Date(); d.setHours(23, 59, 59, 0); return Math.floor(d.getTime() / 1000); })();
  const counts = new Array(n).fill(0);
  const labels = new Array(n);
  const idx = new Map();
  for (let i = 0; i < n; i++) {
    const ts = end - (n - 1 - i) * step;
    labels[i] = hourly ? hourLabel(ts) : dayLabel(ts);
    idx.set(labels[i], i);
  }
  for (const ts of events || []) {
    const l = hourly ? hourLabel(Number(ts)) : dayLabel(Number(ts));
    const i = idx.get(l);
    if (i !== undefined) counts[i] += 1;
  }
  return { counts, labels, hourly };
}

function cumulative(counts) {
  const out = []; let total = 0;
  for (const c of counts) { total += c; out.push(total); }
  return out;
}

function axisLine(labels, width) {
  // Three evenly spaced tick labels under the chart (year stripped).
  const mid = Math.floor((labels.length - 1) / 2);
  const pick = [labels[0], labels[mid], labels[labels.length - 1]].map((l) => l.slice(5));
  const text = pick.join('');
  const gap = Math.max(2, Math.floor((width - text.length) / 2));
  return pick.join(' '.repeat(gap));
}

function fmtTime(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return `${dayLabel(ts)} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export default function register(sdk) {
  const { Box, Dialog, Overlay, Text, defineWidgetApp, h, sparkRows } = sdk;

  function tableRows(state, t) {
    if (state.rows.length === 0) {
      return [h(Text, { key: 'empty', color: t.color.muted }, 'No skill loads recorded in this session/period yet.')];
    }
    const page = state.rows.slice(state.page * TABLE_LIMIT, state.page * TABLE_LIMIT + TABLE_LIMIT);
    return page.map((r, i) => {
      const selected = state.page * TABLE_LIMIT + i === state.selected;
      const marker = selected ? '>' : ' ';
      const name = (marker + ' ' + r.name).padEnd(24).slice(0, 24);
      const cat = r.category.padEnd(14).slice(0, 14);
      const loads = String(r.loads).padStart(4);
      const pct = (r.pct.toFixed(1) + '%').padStart(6);
      const spark = sparkRows(bucketize(r.events, state.days).counts, 6, 1)[0] || '';
      return h(Text, { key: r.name, color: selected ? t.color.primary : t.color.text },
        `${name} ${cat} ${loads} ${pct}  ${spark}`);
    });
  }

  function chartView(state, t) {
    const r = state.rows[state.selected];
    if (!r) return h(Text, { color: t.color.muted }, 'No skill selected.');
    const { counts, labels, hourly } = bucketize(r.events, state.days);
    const data = state.chart === 'line' ? cumulative(counts) : counts;
    const kind = state.chart === 'line' ? 'cumulative (line)' : 'daily (bar)';
    const axis = hourly ? 'hourly x-axis' : 'daily x-axis';
    const rows = sparkRows(data, 52, 7);
    return h(Box, { flexDirection: 'column' },
      h(Text, { bold: true, color: t.color.label }, `${r.name} — ${r.loads} loads · ${kind} · ${axis}`),
      ...rows.map((row, i) => h(Text, { key: `r${i}`, color: t.color.primary }, row)),
      h(Text, { color: t.color.muted }, axisLine(labels, 52)),
      h(Text, { color: t.color.muted }, 'Left/Right: bar <-> line · Up/Down: skill · 1-6: period · Esc: back'));
  }

  defineWidgetApp({
    id: 'skill-stats',
    help: 'skill usage stats (session): arrows select, Enter chart, 1-6 period, Left/Right bar/line',
    mode: 'modal',

    init() {
      const { doc, scope, sessionFile } = loadScopeStats();
      const cats = loadCategories();
      const days = PERIODS[DEFAULT_PERIOD_IDX];
      const { rows, total } = buildRows(doc, cats, days);
      return {
        scope, sessionFile, cats, days, rows, total,
        selected: 0, view: 'table', chart: 'bar', page: 0,
      };
    },

    reduce(state, { ch, key }) {
      const periodKeys = { 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5 };
      const setPeriod = (s, idx) => {
        const days = PERIODS[idx];
        if (days === s.days) return s; // same object: no re-render
        const { rows } = buildRows(loadScopeStats().doc, s.cats, days);
        return { ...s, days, rows, selected: 0, page: 0 };
      };
      if (state.view === 'chart') {
        if (key.escape) return { ...state, view: 'table' };
        if (key.leftArrow || key.rightArrow || ch === 'h' || ch === 'l') {
          return { ...state, chart: state.chart === 'bar' ? 'line' : 'bar' };
        }
        if (ch in periodKeys) return setPeriod(state, periodKeys[ch]);
        if (key.upArrow || ch === 'k') {
          if (state.rows.length === 0) return state;
          return { ...state, selected: (state.selected - 1 + state.rows.length) % state.rows.length };
        }
        if (key.downArrow || ch === 'j') {
          if (state.rows.length === 0) return state;
          return { ...state, selected: (state.selected + 1) % state.rows.length };
        }
        if (ch === 'q') return null;
        return state;
      }
      if (key.escape || ch === 'q') return null;
      if (ch in periodKeys) return setPeriod(state, periodKeys[ch]);
      if (state.rows.length === 0) return state;
      if (key.upArrow || ch === 'k') {
        const sel = (state.selected - 1 + state.rows.length) % state.rows.length;
        return { ...state, selected: sel, page: Math.floor(sel / TABLE_LIMIT) };
      }
      if (key.downArrow || ch === 'j') {
        const sel = (state.selected + 1) % state.rows.length;
        return { ...state, selected: sel, page: Math.floor(sel / TABLE_LIMIT) };
      }
      if (key.return || ch === ' ') return { ...state, view: 'chart' };
      return state;
    },

    render({ state, t }) {
      const periodLabel = `period ${state.days}d · keys 1-6 · ${TABLE_LIMIT}/page`;
      const scopeLabel = state.scope === 'session' ? `session ${state.sessionFile}` : 'global (no session yet)';
      return h(Overlay, null,
        h(Dialog, { width: 64 },
          h(Text, { bold: true, color: t.color.label }, `Skill Stats — ${scopeLabel}`),
          h(Text, { color: t.color.muted }, periodLabel),
          state.view === 'chart'
            ? chartView(state, t)
            : h(Box, { flexDirection: 'column' },
                ...tableRows(state, t),
                h(Text, { color: t.color.muted }, '↑/↓ select · Enter chart · 1-6 period · Esc close'))));
    },
  });
}

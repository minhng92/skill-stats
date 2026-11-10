/**
 * skill-stats — interactive skill usage viewer for the Hermes TUI.
 *
 * Copy to $HERMES_HOME/tui-widgets/skill-stats.mjs (see README), then
 * `/widgets-reload` and `/skill-stats`.
 *
 * Modal flow:
 *   table: Up/Down select a skill, Enter opens its chart, Esc/q closes
 *   chart: Left/Right toggles bar (daily) <-> line (cumulative),
 *          Up/Down switches skill, Esc back to table
 *
 * Data: read directly from $HERMES_HOME/skill-stats/global.json (written by
 * the skill-stats plugin); no network, no backend.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DAYS = 30;

function loadStats() {
  const home = process.env.HERMES_HOME || path.join(os.homedir(), '.hermes');
  const file = path.join(home, 'skill-stats', 'global.json');
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return { skills: {}, total_loads: 0 };
  }
}

function dayKey(ts) {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function buildSeries(events) {
  const counts = new Array(DAYS).fill(0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const idx = new Map();
  for (let i = 0; i < DAYS; i++) {
    const d = new Date(today.getTime() - (DAYS - 1 - i) * 86400000);
    idx.set(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`, i);
  }
  for (const ts of events || []) {
    const i = idx.get(dayKey(ts));
    if (i !== undefined) counts[i] += 1;
  }
  return counts;
}

function cumulative(counts) {
  const out = [];
  let total = 0;
  for (const c of counts) { total += c; out.push(total); }
  return out;
}

export default function register(sdk) {
  const { Box, Dialog, Overlay, Text, defineWidgetApp, h, sparkRows } = sdk;

  function tableRows(state, t) {
    if (state.skills.length === 0) {
      return [h(Text, { key: 'empty', color: t.color.muted }, 'No skill loads recorded yet — load a skill in chat first.')];
    }
    return state.skills.map((s, i) => {
      const selected = i === state.selected;
      const marker = selected ? '>' : ' ';
      const name = (marker + ' ' + s.name).padEnd(34);
      const count = String(s.loads).padStart(4);
      const spark = sparkRows(state.series[s.name] || [], 16, 1)[0] || '';
      return h(Text, { key: s.name, color: selected ? t.color.primary : t.color.text },
        `${name} ${count}  ${spark}`);
    });
  }

  function chartView(state, t) {
    const skill = state.skills[state.selected];
    if (!skill) return h(Text, { color: t.color.muted }, 'No skill selected.');
    const daily = state.series[skill.name] || [];
    const data = state.chart === 'line' ? cumulative(daily) : daily;
    const label = state.chart === 'line' ? 'cumulative (line)' : 'daily (bar)';
    const rows = sparkRows(data, 52, 7);
    return h(Box, { flexDirection: 'column' },
      h(Text, { bold: true, color: t.color.label }, `${skill.name} — ${skill.loads} loads · ${label}`),
      ...rows.map((row, i) => h(Text, { key: `r${i}`, color: t.color.primary }, row)),
      h(Text, { color: t.color.muted }, 'Left/Right: bar <-> line · Up/Down: skill · Esc: back'));
  }

  defineWidgetApp({
    id: 'skill-stats',
    help: 'skill usage stats: arrows select, Enter chart, Left/Right bar/line',
    mode: 'modal',

    init() {
      const doc = loadStats();
      const skills = Object.entries(doc.skills || {})
        .map(([name, v]) => ({ name, loads: Number(v.loads || 0), last_used: Number(v.last_used || 0) }))
        .sort((a, b) => b.loads - a.loads || a.name.localeCompare(b.name));
      const series = {};
      for (const s of skills) series[s.name] = buildSeries((doc.skills[s.name] || {}).events);
      return { skills, series, selected: 0, view: 'table', chart: 'bar' };
    },

    reduce(state, { ch, key }) {
      if (state.view === 'chart') {
        if (key.escape) return { ...state, view: 'table' };
        if (key.leftArrow || key.rightArrow || ch === 'h' || ch === 'l') {
          return { ...state, chart: state.chart === 'bar' ? 'line' : 'bar' };
        }
        if (key.upArrow || ch === 'k') {
          return { ...state, selected: (state.selected - 1 + state.skills.length) % Math.max(1, state.skills.length) };
        }
        if (key.downArrow || ch === 'j') {
          return { ...state, selected: (state.selected + 1) % Math.max(1, state.skills.length) };
        }
        if (ch === 'q') return null;
        return state;
      }
      if (key.escape || ch === 'q') return null;
      if (state.skills.length === 0) return state;
      if (key.upArrow || ch === 'k') {
        return { ...state, selected: (state.selected - 1 + state.skills.length) % state.skills.length };
      }
      if (key.downArrow || ch === 'j') {
        return { ...state, selected: (state.selected + 1) % state.skills.length };
      }
      if (key.return || ch === ' ') return { ...state, view: 'chart' };
      return state;
    },

    render({ state, t }) {
      return h(Overlay, null,
        h(Dialog, { width: 64 },
          h(Text, { bold: true, color: t.color.label }, 'Skill Stats — global'),
          state.view === 'chart'
            ? chartView(state, t)
            : h(Box, { flexDirection: 'column' },
                ...tableRows(state, t),
                h(Text, { color: t.color.muted }, '↑/↓ select · Enter chart · Esc close'))));
    },
  });
}

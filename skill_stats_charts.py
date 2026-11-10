"""Text charts for skill-stats (terminal / slash-command output).

Daily buckets -> unicode column charts. ``bar`` shows per-day loads;
``line`` (cumulative / accumulated) shows the running total — the same two
kinds the Dashboard tab and TUI widget offer, so all three surfaces agree.
"""

from __future__ import annotations

from typing import Any

_BLOCKS = "▁▂▃▄▅▆▇█"
_LEVELS = len(_BLOCKS)


def cumulative(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Running-total version of a daily series: ``[{date, loads: cum}, ...]``."""
    out, total = [], 0
    for row in series:
        total += int(row.get("loads", 0))
        out.append({"date": row["date"], "loads": total})
    return out


def _column(value: int, max_value: int) -> str:
    if max_value <= 0 or value <= 0:
        return " "
    level = max(1, round(_LEVELS * value / max_value))
    return _BLOCKS[min(level, _LEVELS) - 1]


def bar_chart(series: list[dict[str, Any]], width: int = 30) -> str:
    """One-row column chart: ``▂▃▅▇█▆ ...`` plus a compact axis line."""
    if not series:
        return "(no data)"
    max_value = max((int(r.get("loads", 0)) for r in series), default=0)
    columns = "".join(_column(int(r.get("loads", 0)), max_value) for r in series[-width:])
    first = series[-width]["date"][5:] if len(series) >= width else series[0]["date"][5:]
    last = series[-1]["date"][5:]
    return f"{columns}  ({first}..{last}, max {max_value})"


def render_chart(skill_name: str, series: list[dict[str, Any]], kind: str = "bar") -> str:
    """Full text chart: title + column row + per-day loads for non-empty days."""
    data = cumulative(series) if kind == "line" else series
    label = "cumulative" if kind == "line" else "daily"
    lines = [f"{skill_name} — {label} loads ({series[0]['date']}..{series[-1]['date']})" if series else f"{skill_name} — no data",
             bar_chart(data)]
    nonzero = [(r["date"][5:], int(r.get("loads", 0))) for r in data if int(r.get("loads", 0))]
    if nonzero:
        per_day = "  ".join(f"{d}:{n}" for d, n in nonzero[-10:])
        lines.append(f"  {per_day}")
    return "\n".join(lines)

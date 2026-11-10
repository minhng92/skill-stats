"""Time series + text charts."""

from __future__ import annotations

import time

from skill_stats_plugin import skill_stats_charts as charts
from skill_stats_plugin import skill_stats_store as store


def _seed(tmp_path):
    now = int(time.time())
    store.record_usage("hermes-agent", "s1", tmp_path)
    # backdate one event by rewriting the file
    p = store._global_path(tmp_path)
    doc = store._load_stats(p)
    doc["skills"]["hermes-agent"]["events"] = [now, now - 86400, now - 2 * 86400]
    store._save_stats(p, doc)
    return now


def test_events_recorded_and_capped(tmp_path):
    for _ in range(5):
        store.record_usage("pdf", "s1", tmp_path)
    doc = store._load_stats(store._global_path(tmp_path))
    assert len(doc["skills"]["pdf"]["events"]) == 5
    assert doc["skills"]["pdf"]["loads"] == 5


def test_daily_buckets(tmp_path):
    _seed(tmp_path)
    series = store.get_series("hermes-agent", days=30, data_dir=tmp_path)
    assert len(series) == 30
    assert sum(r["loads"] for r in series) == 3
    assert series[-1]["loads"] == 1  # today
    assert series[-2]["loads"] == 1  # yesterday


def test_series_all_skips_empty(tmp_path):
    store.record_usage("pdf", "s1", tmp_path)
    all_series = store.get_series_all(days=7, data_dir=tmp_path)
    assert list(all_series) == ["pdf"]


def test_cumulative():
    series = [{"date": f"2026-01-{i+1:02d}", "loads": c} for i, c in enumerate([1, 0, 2])]
    cum = charts.cumulative(series)
    assert [r["loads"] for r in cum] == [1, 1, 3]


def test_bar_chart_renders():
    series = [{"date": f"2026-01-{i+1:02d}", "loads": c} for i, c in enumerate([0, 3, 1])]
    text = charts.bar_chart(series)
    assert "max 3" in text
    rendered = charts.render_chart("pdf", series, "line")
    assert "cumulative" in rendered and "pdf" in rendered


def test_legacy_file_without_events(tmp_path):
    # pre-v1.2 file: no events key -> loads fine, empty series
    import json
    p = store._global_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"skills": {"pdf": {"count": 2, "last_used": 1}}, "total_loads": 2, "updated_at": 1}))
    stats = store.get_stats("global", data_dir=tmp_path)
    assert stats["total_loads"] == 2
    assert store.get_series("pdf", data_dir=tmp_path)[-1]["loads"] == 0

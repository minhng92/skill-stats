"""Store: counting, session isolation, reset, formatting."""

from __future__ import annotations

import json
from pathlib import Path

from skill_stats_plugin import skill_stats_store as store


def test_record_and_global_stats(tmp_path):
    store.record_usage("hermes-agent", "sess-1", tmp_path)
    store.record_usage("hermes-agent", "sess-1", tmp_path)
    store.record_usage("pdf", "sess-2", tmp_path)
    g = store.get_stats("global", data_dir=tmp_path)
    assert g["total_loads"] == 3
    assert g["skills"][0]["skill"] == "hermes-agent" and g["skills"][0]["loads"] == 2
    assert g["skills"][1]["skill"] == "pdf"
    assert json.loads((tmp_path / "global.json").read_text())["total_loads"] == 3


def test_session_stats_are_isolated(tmp_path):
    store.record_usage("hermes-agent", "sess-1", tmp_path)
    store.record_usage("pdf", "sess-2", tmp_path)
    assert [r["skill"] for r in store.get_stats("session", "sess-1", tmp_path)["skills"]] == ["hermes-agent"]
    assert [r["skill"] for r in store.get_stats("session", "sess-2", tmp_path)["skills"]] == ["pdf"]
    assert store.get_stats("global", data_dir=tmp_path)["total_loads"] == 2


def test_reset_global_clears_sessions(tmp_path):
    store.record_usage("pdf", "s1", tmp_path)
    store.reset_stats("global", data_dir=tmp_path)
    assert store.get_stats("global", data_dir=tmp_path)["total_loads"] == 0
    assert store.get_stats("session", "s1", tmp_path)["total_loads"] == 0


def test_format_and_empty(tmp_path):
    assert "no skill loads recorded in this period" in store.format_table(store.get_table("global", data_dir=tmp_path))
    store.record_usage("pdf", "s1", tmp_path)
    assert "pdf" in store.format_table(store.get_table("global", data_dir=tmp_path))


def test_format_header(tmp_path):
    store.record_usage("pdf", "s1", tmp_path)
    out = store.format_table(store.get_table("global", data_dir=tmp_path))
    assert "total loads (1d): 1" in out
    assert "period: 1d" in out
    assert "last stats" not in out  # attribute removed from the header
    assert "|" in out and "+-" in out  # bordered ASCII table


def test_skill_categories(tmp_path):
    home = tmp_path / "hermes"
    (home / "skills" / "software-development" / "ub-mode").mkdir(parents=True)
    (home / "skills" / "software-development" / "ub-mode" / "SKILL.md").write_text("# ub-mode")
    (home / "skills" / "top-skill").mkdir(parents=True)
    (home / "skills" / "top-skill" / "SKILL.md").write_text("# top")
    (home / "skills" / ".archive" / "hidden").mkdir(parents=True)
    (home / "skills" / ".archive" / "hidden" / "SKILL.md").write_text("# hidden")
    cats = store.skill_categories(home)
    assert cats["ub-mode"] == "software-development"
    assert cats["top-skill"] == ""  # no category folder
    assert "hidden" not in cats  # dot-dirs ignored
    assert store.skill_categories(home).get("nope") is None


def test_period_table_pct_and_category(tmp_path):
    store.record_usage("a", "s1", tmp_path)
    store.record_usage("a", "s1", tmp_path)
    store.record_usage("b", "s1", tmp_path)
    table = store.get_table("global", data_dir=tmp_path, days=1)
    rows = {r["skill"]: r for r in table["skills"]}
    assert rows["a"]["loads"] == 2 and rows["b"]["loads"] == 1
    assert rows["a"]["pct"] == 66.67 and rows["b"]["pct"] == 33.33
    assert rows["a"]["category"] == ""  # no skills dir -> blank
    assert table["total_loads"] == 3
    assert table["skills"][0]["skill"] == "a"  # sorted by loads desc


def test_period_window_filters_old_events(tmp_path):
    import time as _time
    store.record_usage("old", "s1", tmp_path)
    p = store._global_path(tmp_path)
    doc = store._load_stats(p)
    now = int(_time.time())
    doc["skills"]["old"]["events"] = [now - 5 * 86400, now - 10]
    doc["skills"]["old"]["loads"] = 2
    store._save_stats(p, doc)
    fresh = store.get_table("global", data_dir=tmp_path, days=1)
    assert {r["skill"] for r in fresh["skills"] if r["loads"] > 0} == {"old"}  # 1 event in window
    assert next(r for r in fresh["skills"] if r["skill"] == "old")["loads"] == 1
    all_time = store.get_table("global", data_dir=tmp_path, days=0)
    assert next(r for r in all_time["skills"] if r["skill"] == "old")["loads"] == 2


def test_group_by_category(tmp_path):
    home = tmp_path / "hermes"
    for cat, skill in (("cat1", "s1"), ("cat1", "s2"), ("cat2", "s3")):
        (home / "skills" / cat / skill).mkdir(parents=True)
        (home / "skills" / cat / skill / "SKILL.md").write_text("# x")
    store.record_usage("s1", "sess", tmp_path)
    store.record_usage("s1", "sess", tmp_path)
    store.record_usage("s2", "sess", tmp_path)
    store.record_usage("s3", "sess", tmp_path)
    table = store.get_table("global", data_dir=tmp_path, days=1)
    grouped = store.group_by_category(table)
    rows = {r["category"]: r for r in grouped["skills"]}
    assert rows["cat1"]["loads"] == 3 and rows["cat2"]["loads"] == 1
    assert rows["cat1"]["pct"] == 75.0 and rows["cat2"]["pct"] == 25.0
    assert rows["cat1"]["last_used"] >= rows["cat2"]["last_used"]


def test_hourly_buckets_for_short_periods(tmp_path):
    import time as _time
    now = int(_time.time())
    store.record_usage("pdf", "s1", tmp_path)
    p = store._global_path(tmp_path)
    doc = store._load_stats(p)
    doc["skills"]["pdf"]["events"] = [now, now - 3600 * 5]
    store._save_stats(p, doc)
    hourly = store.get_series("pdf", days=1, data_dir=tmp_path)
    assert len(hourly) == 24
    assert all("T" in r["date"] for r in hourly)  # hour labels
    assert sum(r["loads"] for r in hourly) == 2
    daily = store.get_series("pdf", days=7, data_dir=tmp_path)
    assert len(daily) == 7 and all("T" not in r["date"] for r in daily)
    assert store.get_series("pdf", days=1, data_dir=tmp_path, granularity="day")[0]["date"].count("-") == 2


def test_resolve_session_id(tmp_path, monkeypatch):
    sdir = tmp_path / "sessions"
    sdir.mkdir()
    (sdir / "local-c12c3f0c1d37f66b28c07eeb39fa643ce2cd557b065369c3f7eb313bc2d71cab.json").write_text("{}")
    (sdir / "20261110_160607_68b24c.json").write_text("{}")
    # exact id wins
    sid, how = store.resolve_session_id("20261110_160607_68b24c", tmp_path)
    assert (sid, how) == ("20261110_160607_68b24c", "exact")
    # short-form prefix resolves to the full id
    sid, how = store.resolve_session_id("local-c12c3f0c1d37f66b", tmp_path)
    assert how == "prefix" and sid.startswith("local-c12c3f0c1d37f66b")
    assert len(sid) > len("local-c12c3f0c1d37f66b")
    # ambiguous prefix -> most recently modified file
    import os
    amb = sdir / "local-aaa111.json"
    amb.write_text("{}")
    os.utime(amb, (0, 0))  # older than the other one
    sid, how = store.resolve_session_id("local-", tmp_path)
    assert how == "prefix" and sid == "local-c12c3f0c1d37f66b28c07eeb39fa643ce2cd557b065369c3f7eb313bc2d71cab"
    # title lookup via Hermes state.db
    import sqlite3
    db = sqlite3.connect(tmp_path / "state.db")
    db.execute("CREATE TABLE sessions (id TEXT, chat_id TEXT, title TEXT, display_name TEXT, "
               "last_activity_at INTEGER, started_at INTEGER)")
    db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, 99, 1)",
               ("local-c12c3f0c1d37f66b28c07eeb39fa643ce2cd557b065369c3f7eb313bc2d71cab", None,
                "stageshow-bentora", None))
    db.commit(); db.close()
    monkeypatch.setattr(store, "_hermes_home", lambda: tmp_path)
    sid, how = store.resolve_session_id("stageshow-bentora", tmp_path)
    assert how == "title" and sid.startswith("local-c12c3f0c1d37f66b")
    # nothing matches -> empty + "none"
    assert store.resolve_session_id("nope-nothing", tmp_path) == ("", "none")
    assert store.resolve_session_id("", tmp_path) == ("", "none")


def test_pins_roundtrip(tmp_path):
    assert store.get_pins(tmp_path) == []
    store.set_pins(["b", "a", "b", " "], tmp_path)
    assert store.get_pins(tmp_path) == ["b", "a"]  # deduped, stripped, order kept
    assert store.toggle_pin("c", tmp_path) == ["b", "a", "c"]
    assert store.toggle_pin("b", tmp_path) == ["a", "c"]


def test_render_table_borders_and_alignment():
    out = store.render_table(["Skill", "Loads"], [["abc", 3], ["de", 12]], ["l", "r"])
    lines = out.splitlines()
    assert lines[0].startswith("+") and set(lines[0]) <= {"+", "-"}
    assert "| SKILL | LOADS |" in out
    assert "| abc   |     3 |" in out
    assert "| de    |    12 |" in out
    bold = store.render_table(["S"], [["x"]], bold=True)
    assert "\x1b[1m" in bold  # ANSI bold headers on a TTY


def test_data_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_STATS_DIR", str(tmp_path / "custom"))
    assert store._data_dir() == tmp_path / "custom"
    monkeypatch.setenv("SKILL_ANALYTICS_DIR", str(tmp_path / "legacy"))
    monkeypatch.delenv("SKILL_STATS_DIR")
    assert store._data_dir() == tmp_path / "legacy"  # legacy fallback

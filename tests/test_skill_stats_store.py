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
    assert "no skill loads" in store.format_stats(store.get_stats("global", data_dir=tmp_path))
    store.record_usage("pdf", "s1", tmp_path)
    assert "pdf" in store.format_stats(store.get_stats("global", data_dir=tmp_path))


def test_format_header(tmp_path):
    g = store.get_stats("global", data_dir=tmp_path)
    expected = f"total loads: {g['total_loads']} · unique skills: {g['unique_skills']} · last stats: {g['last_stats']}"
    assert expected in store.format_stats(g)


def test_data_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_STATS_DIR", str(tmp_path / "custom"))
    assert store._data_dir() == tmp_path / "custom"
    monkeypatch.setenv("SKILL_ANALYTICS_DIR", str(tmp_path / "legacy"))
    monkeypatch.delenv("SKILL_STATS_DIR")
    assert store._data_dir() == tmp_path / "legacy"  # legacy fallback

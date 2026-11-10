"""Hooks: only skill_view counts; /skill-stats defaults to session."""

from __future__ import annotations

from pathlib import Path

from skill_stats_plugin import skill_stats_hooks as hooks
from skill_stats_plugin import skill_stats_store as store


def test_pre_tool_call_counts_only_skill_view(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)
    assert hooks.on_pre_tool_call("skill_view", {"name": "pdf"}, session_id="s1") is None
    assert hooks.on_pre_tool_call("terminal", {"command": "ls"}, session_id="s1") is None
    assert hooks.on_pre_tool_call("skill_view", {}, session_id="s1") is None
    g = store.get_stats("global", data_dir=tmp_path)
    assert g["total_loads"] == 1 and g["skills"][0]["skill"] == "pdf"


def test_slash_defaults_to_session(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)
    store.record_usage("pdf", "sess-9", tmp_path)
    out = hooks.on_skill_stats("", session_id="sess-9")
    assert "session" in out and "pdf" in out
    assert "global" in hooks.on_skill_stats("global", session_id="sess-9")
    assert "reset" in hooks.on_skill_stats("reset", session_id="sess-9").lower()
    assert store.get_stats("session", "sess-9", tmp_path)["total_loads"] == 0
    assert store.get_stats("global", data_dir=tmp_path)["total_loads"] == 1  # global untouched

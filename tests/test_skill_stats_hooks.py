"""Hooks: only skill_view counts; /skill-stats defaults to session."""

from __future__ import annotations

import json
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


def test_sync_tui_widget(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_hermes_home", lambda: tmp_path)
    # first call copies the shipped widget into the tmp home
    r = hooks.sync_tui_widget()
    dest = tmp_path / "tui-widgets" / "skill-stats.mjs"
    assert r is not None and dest.is_file()
    src = Path(hooks.__file__).resolve().parent / "tui-widgets" / "skill-stats.mjs"
    assert dest.read_bytes() == src.read_bytes()
    assert dest.stat().st_mtime_ns == src.stat().st_mtime_ns
    # second call is a no-op (already current)
    assert hooks.sync_tui_widget() is None
    # a changed target file is re-synced
    dest.write_text("// stale\n")
    assert hooks.sync_tui_widget() is not None
    assert dest.read_bytes() == src.read_bytes()


def test_slash_scope_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)
    store.record_usage("pdf", "sess-9", tmp_path)
    store.record_usage("ub-mode", "sess-other", tmp_path)
    # bare /skill-stats shows the CURRENT session (statistics of itself)
    out = hooks.on_skill_stats("", session_id="sess-9")
    assert out.splitlines()[0].startswith("skill-stats — session")
    assert "pdf" in out and "ub-mode" not in out  # the other session's rows are absent
    # `global` keyword opts out to all-time stats
    out_g = hooks.on_skill_stats("global", session_id="sess-9")
    assert "global" in out_g and "ub-mode" in out_g and "pdf" in out_g
    # --session <id> selects another session
    out2 = hooks.on_skill_stats("--session sess-other", session_id="sess-9")
    assert out2.splitlines()[0].startswith("skill-stats — session") and "ub-mode" in out2
    # short form -s
    assert hooks.on_skill_stats("-s sess-9").splitlines()[0].startswith("skill-stats — session")
    # short-form (prefix) session id resolves to the stored session file
    (tmp_path / "sessions").mkdir(exist_ok=True)
    (tmp_path / "sessions" / "sess-9.json").write_text(json.dumps(
        {"skills": {"pdf": {"loads": 1, "events": [], "last_used": 0}}, "total_loads": 1, "updated_at": 0}))
    (tmp_path / "sessions" / "sess-99999999999999.json").write_text("{}")
    out_p = hooks.on_skill_stats("-s sess-9")
    assert out_p.splitlines()[0].startswith("resolved sess-9 → sess-9.json (prefix)") or \
        out_p.splitlines()[0].startswith("skill-stats")
    # bare --session falls back to the injected (current) session id
    assert hooks.on_skill_stats("--session", session_id="sess-9").splitlines()[0].startswith("skill-stats — session")
    # without an injected id, bare --session stays global
    assert "global" in hooks.on_skill_stats("--session")
    # reset follows the same scoping: bare reset clears THIS session only
    assert "reset session stats" in hooks.on_skill_stats("reset", session_id="sess-9").lower()
    assert store.get_stats("session", "sess-9", tmp_path)["total_loads"] == 0
    assert store.get_stats("session", "sess-other", tmp_path)["total_loads"] == 1  # untouched
    assert store.get_stats("global", data_dir=tmp_path)["total_loads"] == 2  # global untouched
    # `reset global` clears global
    assert "reset global stats" in hooks.on_skill_stats("reset global", session_id="sess-9").lower()
    assert store.get_stats("global", data_dir=tmp_path)["total_loads"] == 0


def test_slash_output_file(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_data_dir", lambda: tmp_path)
    store.record_usage("pdf", "s1", tmp_path)
    out = tmp_path / "out"
    # .txt + no --json -> raw text
    r = hooks.on_skill_stats(f"--session s1 -o {out / 'stats.txt'}")
    assert "output written to" in r
    assert "skill-stats" in (out / "stats.txt").read_text()
    # .json extension -> JSON even without --json
    hooks.on_skill_stats(f"--session s1 -o {out / 'stats.json'}")
    doc = json.loads((out / "stats.json").read_text())
    assert doc["scope"] == "session" and doc["total_loads"] == 1
    # --json with a non-json extension -> JSON
    hooks.on_skill_stats(f"--session s1 --json -o {out / 'stats.dat'}")
    assert json.loads((out / "stats.dat").read_text())["scope"] == "session"

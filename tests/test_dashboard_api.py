"""Dashboard API routes (in-process FastAPI)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skill_stats_plugin import skill_stats_store as store

_API = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    data = tmp_path / "skill-stats"  # where the API's store resolves HERMES_HOME/skill-stats
    store.record_usage("hermes-agent", "s1", data)
    store.record_usage("hermes-agent", "s1", data)
    store.record_usage("pdf", "s1", data)
    spec = importlib.util.spec_from_file_location("skill_stats_papi", _API)
    papi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(papi)
    app = FastAPI()
    app.include_router(papi.router, prefix="/api/plugins/skill-stats")
    return TestClient(app)


def test_overview(client):
    r = client.get("/api/plugins/skill-stats/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["total_loads"] == 3
    assert [s["skill"] for s in body["skills"]] == ["hermes-agent", "pdf"]
    assert sum(row["loads"] for row in body["series"]["hermes-agent"]) == 2


def test_skill_series(client):
    r = client.get("/api/plugins/skill-stats/skills/hermes-agent")
    assert r.status_code == 200
    body = r.json()
    assert body["loads"] == 2
    assert body["series"][-1]["loads"] == 2
    assert body["cumulative"][-1]["loads"] == 2


def test_unknown_skill_404(client):
    assert client.get("/api/plugins/skill-stats/skills/nope").status_code == 404


def test_session_scope(client):
    r = client.get("/api/plugins/skill-stats/session", params={"session_id": "s1"})
    assert r.status_code == 200 and r.json()["total_loads"] == 3
    assert client.get("/api/plugins/skill-stats/session").status_code == 400


def test_profile_param_resolves_profile_data_dir(client, tmp_path):
    """`&profile=<name>` (appended by the dashboard host) reads that profile's
    skill-stats dir, not the server's own HERMES_HOME."""
    pdata = tmp_path / "profiles" / "kyzlab" / "skill-stats"
    store.record_usage("kyz-only-skill", "s1", pdata)
    r = client.get("/api/plugins/skill-stats/overview", params={"profile": "kyzlab"})
    assert r.status_code == 200
    body = r.json()
    assert body["profile"] == "kyzlab"
    assert body["total_loads"] == 1
    assert [s["skill"] for s in body["skills"]] == ["kyz-only-skill"]
    # per-skill route honors the param too
    r2 = client.get("/api/plugins/skill-stats/skills/kyz-only-skill", params={"profile": "kyzlab"})
    assert r2.status_code == 200 and r2.json()["loads"] == 1
    # default/empty profile keeps serving the server's own data dir
    r3 = client.get("/api/plugins/skill-stats/overview", params={"profile": "default"})
    assert r3.json()["profile"] == "default" and r3.json()["total_loads"] == 3
    assert client.get("/api/plugins/skill-stats/overview").json()["total_loads"] == 3
    # unsafe profile names never escape the profiles dir
    r4 = client.get("/api/plugins/skill-stats/overview", params={"profile": "../etc"})
    assert r4.status_code == 200 and r4.json()["profile"] == "default"


def test_overview_period_fields_and_defaults(client):
    r = client.get("/api/plugins/skill-stats/overview")  # default period = 1 day
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 1
    assert body["period_loads"] == 3  # all recorded "now"
    assert body["total_loads"] == 3   # all-time header totals kept
    row = body["skills"][0]
    assert {"skill", "category", "loads", "pct", "last_used"} <= set(row)
    assert row["pct"] == 66.67  # hermes-agent 2/3
    assert body["pins"] == []
    # period filter: nothing 60 days ago is counted, but all-time is unchanged
    r2 = client.get("/api/plugins/skill-stats/overview", params={"days": 60})
    assert r2.json()["period_loads"] == 3 and r2.json()["total_loads"] == 3


def test_skill_series_hourly_for_short_periods(client):
    r = client.get("/api/plugins/skill-stats/skills/hermes-agent", params={"days": 1})
    body = r.json()
    assert body["granularity"] == "hour" and len(body["series"]) == 24
    assert all("T" in row["date"] for row in body["series"])
    r7 = client.get("/api/plugins/skill-stats/skills/hermes-agent", params={"days": 7})
    assert r7.json()["granularity"] == "day" and len(r7.json()["series"]) == 7
    r30 = client.get("/api/plugins/skill-stats/skills/hermes-agent", params={"days": 30})
    assert r30.json()["granularity"] == "day" and len(r30.json()["series"]) == 30


def test_pins_get_post_toggle(client):
    assert client.get("/api/plugins/skill-stats/pins").json()["pins"] == []
    r = client.post("/api/plugins/skill-stats/pins", json={"skill": "hermes-agent"})
    assert r.json() == {"pins": ["hermes-agent"], "skill": "hermes-agent", "pinned": True}
    # pinned skills come back in the overview pins list
    assert client.get("/api/plugins/skill-stats/pins").json()["pins"] == ["hermes-agent"]
    # explicit unpin
    r2 = client.post("/api/plugins/skill-stats/pins", json={"skill": "hermes-agent", "pinned": False})
    assert r2.json()["pins"] == []
    # toggle (no "pinned" field)
    r3 = client.post("/api/plugins/skill-stats/pins", json={"skill": "pdf"})
    assert r3.json()["pins"] == ["pdf"]
    assert client.post("/api/plugins/skill-stats/pins", json={"skill": "pdf"}).json()["pins"] == []
    assert client.post("/api/plugins/skill-stats/pins", json={}).status_code == 400

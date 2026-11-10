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

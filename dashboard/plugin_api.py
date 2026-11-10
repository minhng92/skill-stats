"""Skill Stats dashboard plugin — backend API routes.

Mounted by the Hermes web server at ``/api/plugins/skill-stats/`` once the
plugin is in ``plugins.enabled``. Read-only: serves the counters + daily
time series written by the skill-stats store (``$HERMES_HOME/skill-stats/``).

Routes:
    GET /overview                  global skills sorted by loads desc + totals + 30d series per skill
    GET /skills/{name}?days=30     one skill: daily buckets + cumulative series
    GET /session?session_id=...    same as /overview but for one session
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

_log = logging.getLogger(__name__)
router = APIRouter()

_STORE_MODULE = "hermes_dashboard_plugin_skill_stats_store"


def _store():
    """The sibling ``skill_stats_store`` module, loaded by path (the host imports
    this file via ``spec_from_file_location`` with no package, so a relative
    import is not available)."""
    mod = sys.modules.get(_STORE_MODULE)
    if mod is not None:
        return mod
    path = Path(__file__).resolve().parent.parent / "skill_stats_store.py"
    spec = importlib.util.spec_from_file_location(_STORE_MODULE, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_STORE_MODULE] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(_STORE_MODULE, None)
        raise
    return mod


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def _overview(scope: str = "global", session_id: str = "", days: int = 30) -> dict:
    store = _store()
    days = _clamp(days, 1, 90)
    stats = store.get_stats(scope, session_id=session_id)
    series = store.get_series_all(days=days, scope=scope, session_id=session_id)
    return {
        "scope": scope,
        "session_id": stats.get("session_id", ""),
        "total_loads": stats["total_loads"],
        "unique_skills": stats["unique_skills"],
        "skills": stats["skills"],
        "series": series,
        "days": days,
        "last_stats": stats.get("last_stats", ""),
    }


@router.get("/overview")
async def get_overview(days: int = 30):
    return _overview("global", "", days)


@router.get("/session")
async def get_session(session_id: str = "", days: int = 30):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    return _overview("session", session_id, days)


@router.get("/skills/{name}")
async def get_skill_series(name: str, days: int = 30, scope: str = "global", session_id: str = ""):
    store = _store()
    days = _clamp(days, 1, 90)
    series = store.get_series(name, days=days, scope=scope, session_id=session_id)
    cumulative = []
    total = 0
    for row in series:
        total += int(row["loads"])
        cumulative.append({"date": row["date"], "loads": total})
    stats = store.get_stats(scope, session_id=session_id)
    entry = next((r for r in stats["skills"] if r["skill"] == name), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown skill {name!r}")
    return {"skill": name, "loads": entry["loads"], "last_used": entry["last_used"],
            "days": days, "series": series, "cumulative": cumulative}

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
import re
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


_PROFILE_SAFE = re.compile(r"[A-Za-z0-9_-]+")


def _profile_data_dir(profile: str = ""):
    """Data dir for the dashboard's selected profile.

    The host appends ``&profile=<name>`` to plugin API requests. ``default``
    (or empty) means the server's own ``$HERMES_HOME``; any other profile
    lives at ``$HERMES_HOME/profiles/<name>``. Returns
    ``(skill_stats_dir_or_None, normalized_profile)``; ``None`` lets the
    store resolve on its own. Unsafe names fall back to the default profile.
    """
    if not profile or profile == "default":
        return None, "default"
    if not _PROFILE_SAFE.fullmatch(profile):
        return None, "default"  # never let a query param escape the profiles dir
    base = _store()._hermes_home()
    return base / "profiles" / profile / "skill-stats", profile


def _overview(scope: str = "global", session_id: str = "", days: int = 30,
              profile: str = "") -> dict:
    store = _store()
    days = _clamp(days, 1, 90)
    data_dir, profile = _profile_data_dir(profile)
    # Period-scoped rows (loads/pct/last-used within the window) + all-time totals.
    table = store.get_table(scope, session_id=session_id, data_dir=data_dir, days=days)
    all_stats = store.get_stats(scope, session_id=session_id, data_dir=data_dir)
    series = store.get_series_all(days=days, scope=scope, session_id=session_id, data_dir=data_dir)
    return {
        "scope": scope,
        "session_id": all_stats.get("session_id", ""),
        "total_loads": all_stats["total_loads"],          # all time (header)
        "unique_skills": all_stats["unique_skills"],
        "period_loads": table["total_loads"],             # within the window
        "days": days,
        "skills": table["skills"],                        # rows: skill/category/loads/pct/last_used
        "pins": store.get_pins(data_dir=data_dir),
        "series": series,
        "last_stats": all_stats.get("last_stats", ""),
        "profile": profile,
    }


@router.get("/overview")
async def get_overview(days: int = 1, profile: str = ""):
    return _overview("global", "", days, profile)


@router.get("/session")
async def get_session(session_id: str = "", days: int = 1, profile: str = ""):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    return _overview("session", session_id, days, profile)


@router.get("/pins")
async def get_pins(profile: str = ""):
    data_dir, _ = _profile_data_dir(profile)
    return {"pins": _store().get_pins(data_dir=data_dir)}


@router.post("/pins")
async def post_pin(payload: dict, profile: str = ""):
    """``{"skill": "<name>", "pinned": true|false}`` — true/false pins/unpins;
    omit ``pinned`` to toggle."""
    store = _store()
    skill = str(payload.get("skill", "")).strip()
    if not skill:
        raise HTTPException(status_code=400, detail="skill is required")
    data_dir, _ = _profile_data_dir(profile)
    pinned = payload.get("pinned")
    pins = store.get_pins(data_dir=data_dir)
    if pinned is None:
        pins = store.toggle_pin(skill, data_dir=data_dir)
    elif pinned and skill not in pins:
        pins = store.set_pins(pins + [skill], data_dir=data_dir)
    elif not pinned and skill in pins:
        pins = store.set_pins([p for p in pins if p != skill], data_dir=data_dir)
    return {"pins": pins, "skill": skill, "pinned": skill in pins}


@router.get("/skills/{name}")
async def get_skill_series(name: str, days: int = 1, scope: str = "global",
                           session_id: str = "", profile: str = "",
                           granularity: str = ""):
    store = _store()
    days = _clamp(days, 1, 90)
    data_dir, profile = _profile_data_dir(profile)
    gran = granularity if granularity in ("hour", "day") else None
    series = store.get_series(name, days=days, scope=scope, session_id=session_id,
                              data_dir=data_dir, granularity=gran)
    cumulative = []
    total = 0
    for row in series:
        total += int(row["loads"])
        cumulative.append({"date": row["date"], "loads": total})
    stats = store.get_stats(scope, session_id=session_id, data_dir=data_dir)
    entry = next((r for r in stats["skills"] if r["skill"] == name), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown skill {name!r}")
    table = store.get_table(scope, session_id=session_id, data_dir=data_dir, days=days)
    row = next((r for r in table["skills"] if r["skill"] == name), None)
    return {"skill": name, "loads": entry["loads"], "last_used": entry["last_used"],
            "days": days, "profile": profile, "granularity": "hour" if days <= 3 else "day",
            "period_loads": row["loads"] if row else 0,
            "pct": row["pct"] if row else 0.0,
            "category": row["category"] if row else "",
            "series": series, "cumulative": cumulative}

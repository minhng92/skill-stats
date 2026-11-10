# tests/ — pytest suite

Run from repo root: `python3 -m pytest -q`.

## Conventions
- Import the plugin ONLY as the package alias `skill_stats_plugin`
  (conftest loads the repo root as that package so the relative imports in
  `__init__.py` resolve). Never `import skill_stats_store` top-level and
  never add the repo root to `sys.path` — conftest strips it to avoid
  shadowing core packages.
- The repo root has an `__init__.py`; conftest registers a global plugin
  hook (`_RepoRootIsNotATestPackage`) to collect it as a plain `pytest.Dir`
  — don't remove that hook or pytest tries to import the root `__init__.py`
  standalone and relative imports fail.
- pytest.ini uses `--import-mode=importlib`; keep it.
- Every test gets an isolated `HERMES_HOME` (autouse fixture) —
  `SKILL_STATS_DIR`/`SKILL_ANALYTICS_DIR` are cleared. Use `tmp_path` +
  `monkeypatch` (or `store.record_usage(..., data_dir=tmp_path)`) — never
  touch the real profile home.
- Dashboard API tests use `fastapi.testclient.TestClient` in-process
  (load `dashboard/plugin_api.py` by path, like the test file does);
  FastAPI is the only non-stdlib test dependency.
- Widget logic is verified by `node --check`, not by pytest — pytests cover
  Python only.

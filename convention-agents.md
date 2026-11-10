Sample project's folder structure with nested AGENTS.md files:
```bash
my-project/
├── AGENTS.md            # architecture, shared conventions (loaded at startup)
├── frontend/
│   └── AGENTS.md        # "use pnpm not npm; components in src/components/;
│                        #  Tailwind only, never inline styles; pnpm test"
├── backend/
│   └── AGENTS.md        # "poetry for deps; uvicorn main:app --reload;
│                        #  all endpoints need OpenAPI docstrings"
└── infra/
    └── AGENTS.md        # "terraform state is remote; never run apply locally"
```

The rules for nesting:
- Root file: what EVERY session needs — architecture map, shared conventions, global do-nots
- Nested files: only what's specific to that subtree
- Never repeat root content in nested files — both end up in context together when the subdirectory is discovered, so repetition pays the token tax twice
- Keep nested files small: the 8,000-char per-file cap truncates

**The Production AGENTS.md Template**

- AGENTS.md = the project layer. Architecture, conventions, do-nots. Lives in the repo, belongs to the project.
- Avoid common mistake: writing essays. The AGENTS.md doesn't need prose — it needs a map, rules, and boundaries.
- Structure with ## headers, concrete examples, say what NOT to do, list specific key (paths and ports).

Sample AGENTS.md for reference:
```markdown
# Project Context

Next.js 14 frontend + FastAPI backend, deployed via Docker Compose
on a Hetzner VPS. Repo is a pnpm workspace.

## Architecture
- Frontend: Next.js 14 App Router in /frontend (port 3000)
- Backend: FastAPI + SQLAlchemy in /backend (port 8000)
- Database: PostgreSQL 16 (port 5432), Alembic migrations in /backend/alembic
- Infra: docker-compose.yml at root; staging deploys via ./scripts/deploy-staging.sh

## Conventions
- TypeScript strict mode; no `any` without a comment justifying it
- Python: PEP 8, type hints everywhere, Google-style docstrings
- API responses: {data, error, meta} shape — see backend/app/schemas/envelope.py
- Tests: frontend in __tests__/, backend in tests/ — run with pnpm test / pytest
- Commits: conventional commits, scope required (feat(api): ...)

## Do NOT
- Never edit files in backend/alembic/versions/ by hand — use `alembic revision`
- Never commit .env.local (contains real keys)
- Never add a dependency without noting it in this file's Architecture section
- Don't run the production compose file locally; use docker-compose.dev.yml

## Gotchas
- Frontend dev server needs `pnpm dev --hostname 0.0.0.0` inside Docker or
  HMR breaks
- Alembic autogenerate misses enum changes — always review generated migrations
```

Sizing guidance: keep it under ~2,000 words. If a section grows past that, the details belong in a nested AGENTS.md or in a skill — not the root file. Remember the rent: the agent reads this file every turn.

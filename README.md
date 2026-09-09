# viewBuilder

A visual tool for mapping legacy MS SQL Server tables to new tables/views: drag-link source
columns to target columns on a canvas, translate enum-coded columns to their real values via
versioned lookup tables, and mark rows "retired" as an append-only audit record instead of
mutating the source. Every mapping supports a dry-run preview before a logged, versioned
execution.

This is a FastAPI backend (owns all SQL Server access, mapping/translation validation, enum
translation, retirement-audit writes, and migration execution) paired with a React +
TypeScript frontend (owns only the drag-and-drop mapping canvas and result/log views).

Full spec, data model, API contract, and a detailed step-by-step walkthrough live under
[`specs/001-sql-view-builder/`](specs/001-sql-view-builder/):

- [`spec.md`](specs/001-sql-view-builder/spec.md) — feature spec and requirements
- [`plan.md`](specs/001-sql-view-builder/plan.md) — implementation plan and architecture
- [`data-model.md`](specs/001-sql-view-builder/data-model.md) — metadata store schema
- [`contracts/api.md`](specs/001-sql-view-builder/contracts/api.md) — backend HTTP API contract
- [`quickstart.md`](specs/001-sql-view-builder/quickstart.md) — the canonical setup + golden-path
  walkthrough (this README summarizes it; quickstart.md is the source of truth if the two ever
  disagree)

Non-negotiable project principles (dry-run must never write, enum translation must never
silently guess, retirement is append-only, etc.) are documented in
[`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## Prerequisites

- Python 3.12
- Node 22 (Bun optional for frontend tooling speed)
- Docker, for the local MS SQL Server fixture + Postgres metadata store
- The Microsoft ODBC Driver 18 for SQL Server, if you want the backend to actually reach a
  real SQL Server instance locally (rather than just running the parts of the test suite that
  don't need one — see Testing, below)

## 1. Start local infrastructure

```bash
cd backend/docker
docker compose up -d
# Brings up:
#  - mssql: MS SQL Server, seeded with sample legacy-shaped tables (incl. an enum-coded
#           status column and a sample legacy retirement-reason table) via init script
#  - postgres: the app's own metadata store (exposed on host port 5434)
```

## 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt   # requirements-dev.txt adds
                                                            # pytest/ruff/black for local dev
alembic upgrade head          # create metadata store schema
uvicorn src.api.main:app --reload --port 8000
```

API docs are available at `http://localhost:8000/docs` (FastAPI's built-in OpenAPI UI) — this
should match [`specs/001-sql-view-builder/contracts/api.md`](specs/001-sql-view-builder/contracts/api.md).

The backend reads its metadata-store connection string and other settings from environment
variables / a `.env` file in `backend/` (see `backend/src/settings.py`); the default matches
the `docker-compose.yml` Postgres service above.

## 3. Frontend

```bash
cd frontend
bun install    # or npm install
bun run dev    # Vite dev server on http://localhost:5173, proxies /api to localhost:8000
```

## 4. Try the golden path

There is currently no frontend form for creating a `connection_config` (v1's picker only
lists connections that already exist), so the first step of the golden path goes through the
API directly. The full walkthrough — including this step, drawing links on the canvas,
attaching an enum translation, dry-running, executing, and configuring a retirement mapping —
is in [`quickstart.md`](specs/001-sql-view-builder/quickstart.md#4-try-the-golden-path).

## Tests

```bash
cd backend && source .venv/bin/activate && pytest         # unit + integration + contract
cd frontend && bun run test                                # unit (Vitest)
cd frontend && bun run test:e2e                             # Playwright golden-path e2e
```

Integration tests that need a live MS SQL Server (execution, retirement, schema-drift, enum
dry-run) skip cleanly — rather than failing the suite — when no MS SQL Server / ODBC Driver 18
is reachable, matching the pattern in `backend/tests/integration/test_execute_run.py`. The
Playwright e2e spec (`frontend/tests/e2e/golden-path.spec.ts`) does the same: it skips if the
backend or a live SQL Server isn't reachable, rather than failing.

Lint/format/typecheck, run before every merge:

```bash
cd backend && ruff check . && black --check .
cd frontend && npx tsc -b && npx biome check .
```

## Project structure

```text
backend/
├── src/
│   ├── api/            # FastAPI routers, error shape, audit-logging middleware
│   ├── models/          # SQLAlchemy models for the metadata store
│   ├── services/         # SQL Server introspection, mapping engine, enum translation,
│   │                       retirement-audit writer, dry-run/execute orchestration
│   ├── db/               # Metadata store session/engine, Alembic migrations
│   └── connectors/       # MS SQL Server connection management (source/target, env-tagged)
├── tests/
│   ├── unit/               # enum translation, mapping validation, versioning rules
│   ├── integration/        # against docker-compose MS SQL Server fixture
│   └── contract/           # API contract tests against contracts/api.md
└── docker/
    └── docker-compose.yml  # local MS SQL Server + seeded legacy-shaped sample data

frontend/
├── src/
│   ├── components/
│   │   ├── canvas/         # React Flow-based column mapping canvas
│   │   └── shared/          # ProductionGuard and other cross-page UI safeguards
│   ├── pages/               # Table picker, mapping editor, dry-run results, run history, ...
│   └── services/            # Typed API client for the backend contracts
└── tests/
    ├── unit/
    └── e2e/                 # Playwright: golden-path flow
```

## Environment separation

Connections are tagged `dev`, `test`, or `prod` (`connection_config.environment`). Executing
(not dry-running) a mapping that touches a `prod`-tagged connection requires an explicit
`confirm_production: true` on the request — the backend returns `409
production_confirmation_required` otherwise (FR-016) — and the frontend additionally gates
that action behind a distinct visual warning and a typed confirmation phrase
(`frontend/src/components/shared/ProductionGuard.tsx`).

# viewBuilder

A visual tool for mapping legacy MS SQL Server tables to new tables/views: drag-link source
columns to target columns on a canvas, translate enum-coded columns to their real values via
versioned lookup tables, and mark rows "retired" as an append-only audit record instead of
mutating the source. Every mapping supports a dry-run preview before a logged, versioned
execution.

This is a FastAPI backend (owns all SQL Server access, mapping/translation validation, enum
translation, retirement-audit writes, and migration execution) paired with a React +
TypeScript frontend (owns only the drag-and-drop mapping canvas and result/log views).

A second capability, built on the same backend/frontend, generates and deploys a real SQL
Server VIEW that reconstructs an old wide table's exact column shape from several new
normalized tables (via a join graph + column mapping on the same canvas), reconciles that
view's live output against the still-live old table, and — for anything reconciliation flags
as missing — looks the value up in a separate legacy XML document table.

Full spec, data model, API contract, and a detailed step-by-step walkthrough for each feature
live under:

**001 — legacy table → new table/view mapping, enum translation, retirement**
[`specs/001-sql-view-builder/`](specs/001-sql-view-builder/):

- [`spec.md`](specs/001-sql-view-builder/spec.md) — feature spec and requirements
- [`plan.md`](specs/001-sql-view-builder/plan.md) — implementation plan and architecture
- [`data-model.md`](specs/001-sql-view-builder/data-model.md) — metadata store schema
- [`contracts/api.md`](specs/001-sql-view-builder/contracts/api.md) — backend HTTP API contract
- [`quickstart.md`](specs/001-sql-view-builder/quickstart.md) — the canonical setup + golden-path
  walkthrough (this README summarizes it; quickstart.md is the source of truth if the two ever
  disagree)

**002 — legacy-shape compatibility view, reconciliation, XML fallback**
[`specs/002-legacy-compat-view/`](specs/002-legacy-compat-view/):

- [`spec.md`](specs/002-legacy-compat-view/spec.md) — feature spec and requirements
- [`plan.md`](specs/002-legacy-compat-view/plan.md) — implementation plan and architecture
- [`data-model.md`](specs/002-legacy-compat-view/data-model.md) — metadata store schema
- [`contracts/api.md`](specs/002-legacy-compat-view/contracts/api.md) — backend HTTP API contract
- [`quickstart.md`](specs/002-legacy-compat-view/quickstart.md) — the canonical setup +
  golden-path walkthrough for this feature (source of truth if this README and it ever
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
#  - mssql: MS SQL Server, seeded via init script with:
#             - 001's sample legacy-shaped tables (incl. an enum-coded status column and
#               a sample legacy retirement-reason table)
#             - 002's old wide table (dbo.legacy_loan_application), its 5-table normalized
#               replacement schema (dbo.loan_*), and a legacy XML document table
#               (dbo.legacy_application_xml) — see specs/002-legacy-compat-view/quickstart.md
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

### No-install alternative: SQLite instead of Postgres

If you can't install Docker or Postgres (e.g. a locked-down work machine), point the backend
at a local SQLite file instead — no install, no server process, just a file:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
METADATA_DATABASE_URL="sqlite:///./viewbuilder.db" uvicorn src.api.main:app --reload --port 8000
```

(or put `METADATA_DATABASE_URL=sqlite:///./viewbuilder.db` in `backend/.env` instead of
passing it inline). If only an older ODBC driver is installed, also set
`MSSQL_ODBC_DRIVER="ODBC Driver 17 for SQL Server"` (defaults to Driver 18) — this is
separate from `METADATA_DATABASE_URL`, which is only ever Postgres/SQLite and never touches
this setting. Skip `alembic upgrade head` entirely for this path — a `sqlite:///` URL
makes the app create its own schema from the models directly on startup (there's no prior
data to migrate for a fresh local file), so nothing else about running it differs from the
Postgres path. This is exactly the same metadata store *shape* — connections, mappings, view
definitions, run/reconciliation history — just persisted to a single local file instead of a
server process. If you also can't reach a real MS SQL Server without your own domain login,
use `auth_mode: "windows_integrated"` when creating a connection (via the Setup screen below)
so the backend authenticates as your own logged-in Windows identity (`Trusted_Connection=yes`)
instead of a stored SQL login.

## 3. Frontend

```bash
cd frontend
bun install    # or npm install
bun run dev    # Vite dev server on http://localhost:5173, proxies /api to localhost:8000
```

## 4. Try the golden path

Create a `connection_config` from the frontend's `/setup` screen (choose SQL Login or Windows
Integrated authentication there), then follow the rest of the golden path — drawing links on
the canvas, attaching an enum translation, dry-running, executing, and configuring a
retirement mapping — in [`quickstart.md`](specs/001-sql-view-builder/quickstart.md#4-try-the-golden-path).

## 5. Try the legacy-compat-view golden path (002)

Same backend/frontend, a second flow: capture an old wide table's shape
(`/legacy-shapes/new`), build a join graph + column mapping over its normalized
replacement tables (`/view-definitions/new`), preview and deploy a compatibility view,
reconcile it against the still-live old table, and fall back to a legacy XML document
lookup for anything reconciliation flags as missing. There is no creation UI yet for a
top-level `xml_field_mapping` — that one still goes through the API directly
(`POST /xml-field-mappings`); everything else (capturing a legacy shape, the join-graph
canvas, column mapping, preview/deploy, reconciliation, and adding XML `field_paths`
entries) is driven from the UI. Full walkthrough:
[`specs/002-legacy-compat-view/quickstart.md`](specs/002-legacy-compat-view/quickstart.md#golden-path).

## Tests

```bash
cd backend && source .venv/bin/activate && pytest         # unit + integration + contract
cd frontend && bun run test                                # unit (Vitest)
cd frontend && bun run test:e2e                             # Playwright: both golden-path specs
```

Integration tests that need a live MS SQL Server (execution, retirement, schema-drift, enum
dry-run, view deploy/reconcile/XML-lookup roundtrips) skip cleanly — rather than failing the
suite — when no MS SQL Server / ODBC Driver 18 is reachable, matching the pattern in
`backend/tests/integration/test_execute_run.py`. The Playwright e2e specs
(`frontend/tests/e2e/golden-path.spec.ts` for 001,
`frontend/tests/e2e/legacy-compat-golden-path.spec.ts` for 002) do the same: each skips if the
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
│   │                     (001: connections/mappings/enum_translations/runs;
│   │                      002: legacy_shapes/view_definitions/reconciliation/xml_mappings)
│   ├── models/          # SQLAlchemy models for the metadata store
│   ├── services/         # 001: SQL Server introspection, mapping engine, enum translation,
│   │                       retirement-audit writer, dry-run/execute orchestration
│   │                       002: legacy shape capture/drift, view-definition versioning +
│   │                       DDL generation, view deploy/preview, reconciliation engine,
│   │                       XML lookup
│   ├── db/               # Metadata store session/engine, Alembic migrations
│   └── connectors/       # MS SQL Server connection management (source/target, env-tagged)
├── tests/
│   ├── unit/               # enum translation, mapping/view-definition validation & versioning,
│   │                         DDL generation, reconciliation comparison, XML lookup
│   ├── integration/        # against docker-compose MS SQL Server fixture
│   └── contract/           # API contract tests against each feature's contracts/api.md
└── docker/
    └── docker-compose.yml  # local MS SQL Server + seeded 001 + 002 sample data

frontend/
├── src/
│   ├── components/
│   │   ├── canvas/         # React Flow-based mapping canvas (001) + join-graph canvas (002)
│   │   └── shared/          # ProductionGuard and other cross-page UI safeguards
│   ├── pages/               # 001: table picker, mapping editor, dry-run results, run history, ...
│   │                          002: view-definition editor, view preview/deploy results,
│   │                          reconciliation results, XML lookup panel
│   └── services/            # Typed API client for both features' backend contracts
└── tests/
    ├── unit/
    └── e2e/                 # Playwright: golden-path.spec.ts (001),
                              # legacy-compat-golden-path.spec.ts (002)
```

## Environment separation

Connections are tagged `dev`, `test`, or `prod` (`connection_config.environment`). Executing
(not dry-running) a mapping that touches a `prod`-tagged connection requires an explicit
`confirm_production: true` on the request — the backend returns `409
production_confirmation_required` otherwise (FR-016) — and the frontend additionally gates
that action behind a distinct visual warning and a typed confirmation phrase
(`frontend/src/components/shared/ProductionGuard.tsx`).

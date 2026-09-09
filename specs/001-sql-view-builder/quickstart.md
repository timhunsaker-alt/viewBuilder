# Quickstart: viewBuilder

## Prerequisites

- Python 3.12, Node 22 (Bun optional for frontend tooling speed)
- Docker (for the local MS SQL Server fixture + Postgres metadata store)

## 1. Start local infrastructure

```bash
cd backend/docker
docker compose up -d
# Brings up:
#  - mssql: MS SQL Server, seeded with sample legacy-shaped tables (incl. an enum-coded
#           status column and a sample legacy retirement-reason table) via init script
#  - postgres: the app's own metadata store
```

## 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # create metadata store schema
uvicorn src.api.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs` (FastAPI's built-in OpenAPI UI) — should
match `specs/001-sql-view-builder/contracts/api.md`.

## 3. Frontend

```bash
cd frontend
bun install    # or npm install
bun run dev    # Vite dev server, proxies /api to localhost:8000
```

## 4. Try the golden path

1. Open the frontend, add a `connection_config` pointing at the local seeded `mssql` container
   (`environment: dev`).
2. Pick the sample source table; the canvas shows its columns.
3. Pick/create a target table on the same (or another) connection; drag links from source
   columns to target columns.
4. For the sample enum-coded column, attach the seeded enum-translation table.
5. Save the mapping.
6. Run **Dry Run** — confirm the preview shows translated values and row counts, and that
   nothing was written (re-query the target table to confirm it's still empty/unchanged).
7. Run **Execute** — confirm the target table now has the expected rows and `GET /runs` shows
   a completed `run_log_entry` referencing the mapping version used.
8. Configure a retirement mapping against the sample legacy retirement-reason table; execute
   it; confirm the source row is unchanged and a new row appears in the configured retirement
   audit table with a translated reason.

## Tests

```bash
cd backend && pytest                 # unit + integration (spins up against docker-compose mssql)
cd frontend && bun run test          # unit
cd frontend && bun run test:e2e      # Playwright canvas flow
```

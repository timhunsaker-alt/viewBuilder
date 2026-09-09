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
pip install -r requirements.txt -r requirements-dev.txt   # requirements-dev.txt adds
                                                            # pytest/ruff/black, needed below
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

1. Create a `connection_config` pointing at the local seeded `mssql` container
   (`environment: dev`). There is no frontend form for this yet (v1 has no connection-create
   UI) — use the backend's own Swagger UI at `http://localhost:8000/docs` (`POST /connections`)
   or `curl`, e.g.:
   ```bash
   curl -X POST http://localhost:8000/api/v1/connections \
     -H "Content-Type: application/json" \
     -d '{"name": "Seeded MSSQL", "role": "either", "environment": "dev", \
          "host": "localhost", "port": 1433, "database": "master", \
          "credential_ref": "local-dev-sa"}'
   ```
2. Open the frontend at `http://localhost:5173`, pick that connection, then pick the sample
   source table; the page shows its columns.
3. Click "Continue to mapping canvas →". On the mapping editor, pick a target connection and
   target table (defaults to the same connection/table you started from, but can be pointed at
   a different one, per FR-002); drag links from source columns to target columns on the
   canvas.
4. For the sample enum-coded column, attach the seeded enum-translation table (create it first
   via `POST /enum-translations` if it doesn't already exist — there is likewise no
   translation-table-creation UI wired into this flow yet, only the editor for existing
   tables at `/enum-translations`).
5. Name the mapping and save it.
6. From the mapping editor, click "Run dry run" — confirm the preview shows translated values
   and row counts, and that nothing was written (re-query the target table to confirm it's
   still empty/unchanged).
7. Click **Execute for real** — if either connection is tagged `prod` this is gated behind a
   distinct warning banner and a typed confirmation phrase (`ProductionGuard`,
   `frontend/src/components/shared/ProductionGuard.tsx`); for a `dev`/`test` connection it
   executes immediately. Confirm the target table now has the expected rows and the run
   history page (`/runs`) shows a completed `run_log_entry` referencing the mapping version
   used.
8. Configure a retirement mapping (`/retirement/new`, reached from the table picker) against
   the sample legacy retirement-reason table; save it, then dry-run and execute it from
   `/mappings/{id}/dry-run`; confirm the source row is unchanged and a new row appears in the
   configured retirement audit table with a translated reason.

## Tests

```bash
cd backend && pytest                 # unit + integration (spins up against docker-compose mssql)
cd frontend && bun run test          # unit
cd frontend && bun run test:e2e      # Playwright canvas flow
```

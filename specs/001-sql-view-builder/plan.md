# Implementation Plan: Visual SQL Server View/Mapping Builder

**Branch**: `001-sql-view-builder` | **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-sql-view-builder/spec.md`

## Summary

Build a tool that lets an operator visually map columns from a legacy MS SQL Server table to
a target table/view, translate enum-coded source columns to their real values via versioned
lookup tables, and record row retirement as append-only audit entries rather than mutating the
source. Every mapping supports dry-run preview before a logged, versioned execution. The
system is a FastAPI backend (owns all SQL Server access, mapping/translation validation, enum
translation, retirement-audit writes, and migration execution) paired with a React + TypeScript
frontend (owns only the drag-and-drop mapping canvas and result/log views), with its own
metadata datastore separate from the legacy databases being mapped.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x / Node 22 (frontend build tooling)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x + pyodbc (MS SQL Server access for both
legacy source/target connections and, optionally, the metadata store if SQL Server is chosen
there too), Pydantic v2, Alembic (metadata store migrations); React 18, TypeScript, Vite,
React Flow (node/edge canvas for the column-mapping UI), TanStack Query (API data fetching)

**Storage**: Two distinct storage roles — (1) arbitrary external MS SQL Server instances that
are *targets of introspection/migration* (source and target tables, connection-configured, not
owned by this app), and (2) the app's own metadata store (mapping definitions + versions,
enum-translation tables + versions, retirement audit records are physically written into the
*target* SQL Server database per FR-009/FR-010 — not the metadata store — while run logs and
mapping/translation definitions live in the metadata store). Metadata store: PostgreSQL 16,
accessed only by the backend.

**Testing**: pytest (backend unit + integration, including a docker-compose MS SQL Server
container seeded with sample legacy-shaped tables for integration/dry-run tests per
Constitution Principle V); Vitest + React Testing Library (frontend unit); Playwright (canvas
drag-link end-to-end smoke test)

**Target Platform**: Linux server (backend, containerized), modern evergreen browsers
(frontend)

**Project Type**: Web application (frontend + backend)

**Performance Goals**: Dry-run preview over a 100k-row source table returns within 10s;
canvas remains responsive (no dropped-frame drag interactions) with up to 200 source+target
columns rendered simultaneously

**Constraints**: Backend must never expose raw DB credentials to the frontend (Constitution
Principle VI); execution against a database flagged production requires an explicit second
confirmation and defaults to dry-run first (Constitution Principle VII); enum translation
must fail loudly on unmapped codes, never silently default (Constitution Principle III);
retirement writes are append-only, no update/delete path exposed for them outside an explicit
documented admin correction (Constitution Principle IV)

**Scale/Scope**: Single trusted internal operator for v1 (per spec Assumptions); handful of
legacy source databases/tables per engagement, not a multi-tenant SaaS

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Reviewable, Reversible Migrations | Dry-run is a first-class, separately-testable user story (US4) that performs zero writes; every execution is logged (US5); no drop/truncate/hard-delete paths are exposed anywhere in the API surface | PASS |
| II. Mapping Definitions as Versioned Data | Mapping definitions and enum-translation tables are stored as structured, versioned rows in the metadata store (see data-model.md), never hardcoded; API is CRUD over these, not a code generator | PASS |
| III. Auditable Enum Translation | Enum-translation tables are explicit code→value rows, versioned; FR-008 requires flagging untranslatable codes rather than defaulting — enforced at the service layer with a dedicated test per Constitution Principle V | PASS |
| IV. Retirement Is Append-Only Audit | Retirement writes are modeled as insert-only; no update/delete endpoint is planned for retirement_audit_record; source table is only ever read, never written, by the retirement flow (FR-009) | PASS |
| V. Test-First for Migration Logic | pytest suite required before merge for mapping-run, enum-translation, and retirement-audit code; docker-compose SQL Server fixture enables real integration tests without a live legacy DB | PASS (process gate — enforced at PR review per Constitution's Development Workflow section) |
| VI. Backend/Frontend Separation of Concerns | All SQL and credentials live in the FastAPI backend; frontend only calls the versioned HTTP API (contracts/) for schema discovery, mapping CRUD, dry-run, and execution | PASS |
| VII. Environment Separation | Connection configs are tagged with an environment (dev/test/prod); backend requires an explicit `confirm_production=true`-style flag plus defaults execution endpoints to dry-run unless explicitly told to execute | PASS |

No violations requiring justification — Complexity Tracking section is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-sql-view-builder/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── api/              # FastAPI routers: connections, schema, mappings,
│   │                      translations, runs (dry-run + execute), retirement
│   ├── models/            # SQLAlchemy models for the metadata store
│   │                      (MappingDefinition, MappingVersion, EnumTranslationTable,
│   │                      EnumTranslationVersion, RunLogEntry)
│   ├── services/          # SQL Server introspection, mapping engine, enum
│   │                      translation, retirement-audit writer, dry-run/execute
│   │                      orchestration
│   ├── db/                # Metadata store session/engine, Alembic migrations
│   └── connectors/        # MS SQL Server connection management (source/target,
│                            env-tagged, credential loading)
├── tests/
│   ├── unit/               # enum translation, mapping validation, versioning rules
│   ├── integration/        # against docker-compose MS SQL Server fixture:
│   │                        introspection, dry-run, execute, retirement audit
│   └── contract/           # API contract tests against contracts/
└── docker/
    └── docker-compose.yml  # local MS SQL Server + seeded legacy-shaped sample data

frontend/
├── src/
│   ├── components/
│   │   ├── canvas/         # React Flow-based column mapping canvas
│   │   └── shared/
│   ├── pages/              # Table picker, mapping editor, dry-run results, run history
│   └── services/           # Typed API client for the backend contracts
└── tests/
    ├── unit/
    └── e2e/                # Playwright: drag-link → save → dry-run flow
```

**Structure Decision**: Web application split into `backend/` (FastAPI, owns all SQL access
and business logic per Constitution Principle VI) and `frontend/` (React/TypeScript, canvas +
views only). This is Option 2 (frontend + backend) from the template, chosen because the spec
requires both a database-touching service and a distinct interactive visual canvas that must
never hold credentials.

## Complexity Tracking

*No constitution violations — table intentionally omitted.*

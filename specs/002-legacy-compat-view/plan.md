# Implementation Plan: Legacy-Shape Compatibility View & Reconciliation

**Branch**: `002-legacy-compat-view` | **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-legacy-compat-view/spec.md`

## Summary

Extend viewBuilder with a second capability alongside its existing row-copy migration
engine: generating and deploying a real SQL Server VIEW that reconstructs an old wide
table's exact column shape/order from several new normalized tables (via a
user-configured join graph + column mapping on the existing drag-and-drop canvas),
reconciling that view's live output against the still-live old table, and — for anything
reconciliation flags as missing — looking the value up in a separate legacy XML document
table via a configured field mapping. Reuses the existing FastAPI backend, SQL Server
connector, Postgres metadata store, and React/React Flow frontend; adds DDL
generation/deployment, a multi-table join-graph model, a reconciliation engine, and an
XML lookup service that 001 did not need.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x / Node 22 (frontend) — same as
001-sql-view-builder.

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x + pyodbc, Pydantic v2, Alembic (all
reused from 001); no new backend dependency is required for XML — SQL Server's native
`xml` column type's `.value()`/`.query()` methods are pushed down as plain T-SQL via
SQLAlchemy `text()`, so parsing happens server-side (research.md §1). Frontend reuses
React 18, TypeScript, Vite, React Flow, TanStack Query from 001; the canvas gains a mode
for multiple source-table nodes connected by join-edges, not a new library.

**Storage**: Same two-role split as 001 — arbitrary external MS SQL Server connections
(now including, for this feature, the "old" wide-table connection, the "new" normalized
schema connection(s), and the "XML document store" connection — these MAY be the same
physical connection or different ones, see data-model.md) are read/written via
`connection_config`; the app's own versioned metadata (view definitions, join-graph
config, XML field mappings, deployment logs, reconciliation runs) lives in the existing
Postgres metadata store.

**Testing**: pytest (unit + integration), extending the existing docker-compose MS SQL
Server fixture with: a sample "old wide table," a sample 5-table normalized replacement
schema, and a sample XML document table (research.md §1 sample). Frontend: Vitest +
React Testing Library for the join-graph canvas mode, Playwright for the end-to-end
build → preview → deploy → reconcile → XML-lookup flow.

**Target Platform**: Linux server (backend), evergreen browsers (frontend) — unchanged
from 001.

**Project Type**: Web application (frontend + backend) — extends the existing 001
codebase in place; no new top-level project.

**Performance Goals**: Reconciliation over a 100k-row old table completes within 5
minutes (heavier than a plain dry-run since it's a keyed dual-source row+column compare,
per research.md §2's chunked/hashed comparison strategy); view preview over the same
scale returns within 15s (slightly more than 001's 10s dry-run goal, since a join preview
touches multiple tables).

**Constraints**: Deploying (CREATE OR ALTER VIEW) against a `prod`-tagged connection
requires the same explicit `confirm_production` gate as execution in 001 (Constitution
Principle VII) and defaults to preview-only. Reconciliation and XML lookup are strictly
read-only against every connection they touch — no code path in this feature ever issues
UPDATE/DELETE/DROP against the old table, the new schema, or the XML store. The deployed
view's name MUST NOT collide with the old table's name while both exist (spec
Assumptions) — the tool refuses a deploy that would require dropping/renaming the old
table itself.

**Scale/Scope**: Same single-trusted-operator, no-auth-yet scope as 001. Handful of
legacy-shape/new-schema pairs per engagement, not a multi-tenant SaaS.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Reviewable, Reversible Migrations | Generalizes cleanly to "reviewable, reversible **DDL deploys and comparisons**": every view deploy has a mandatory preview (generated SQL + sample rows) with zero deployment; a bad deploy is reversed by deploying a corrected new version's SQL, never by hand-editing the live view. Reconciliation/XML-lookup are read-only by construction (FR-009/FR-012 never write) | PASS |
| II. Mapping Definitions as Versioned Data | Extends directly: `compatibility_view_definition` + its versions (join graph + column map + generated SQL) follow the exact same append-only versioning shape as `mapping_definition`/`mapping_version` in 001 | PASS |
| III. Auditable Enum Translation | Not applicable to this feature — no enum-coded columns are translated here. (The XML field mapping in US4 is a location lookup, not a code→value translation table; it is still versioned per Principle II's spirit, but Principle III's specific "flag untranslatable codes" rule doesn't map onto it 1:1 — see research.md §3 for how "field not found" plays the equivalent role.) | N/A |
| IV. Retirement Is Append-Only Audit | Not applicable — this feature has no retirement/row-status concept | N/A |
| V. Test-First for Migration Logic | Extended to DDL-generation, join-graph validation, reconciliation-comparison, and XML-extraction logic — all four get test-first coverage per the tasks breakdown, using the same docker-compose MS SQL Server fixture pattern as 001 | PASS |
| VI. Backend/Frontend Separation of Concerns | Unchanged: all SQL (including the generated CREATE VIEW DDL and the XML `.value()` T-SQL) is assembled and executed only in the backend; the frontend's join-graph canvas only calls the versioned API | PASS |
| VII. Environment Separation | Unchanged mechanism, extended scope: the `confirm_production` gate now also guards view deployment (not just row-copy execution), since deploying DDL against a `prod`-tagged connection is at least as consequential as writing rows | PASS |

No violations requiring justification — Complexity Tracking section is not needed. Note:
this plan generalizes several 001 principles (worded around "migrations"/"mapping
definitions") to this feature's DDL-deployment and multi-source-comparison mechanics
rather than proposing a constitution amendment — the underlying safety properties
(reviewable, versioned, tested, separated, environment-aware) are identical in spirit.

## Project Structure

### Documentation (this feature)

```text
specs/002-legacy-compat-view/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root — extends the existing 001 layout in place)

```text
backend/
├── src/
│   ├── api/
│   │   ├── view_definitions.py   # NEW: CRUD + preview + deploy for compatibility views
│   │   ├── reconciliation.py     # NEW: run + fetch reconciliation results
│   │   └── xml_mappings.py       # NEW: CRUD for XML field mappings + lookup endpoint
│   ├── models/
│   │   ├── legacy_shape.py               # NEW: LegacyShapeCapture
│   │   ├── view_definition.py            # NEW: ViewDefinition + ViewDefinitionVersion
│   │   ├── deployment_log.py             # NEW: ViewDeploymentLogEntry
│   │   ├── reconciliation.py             # NEW: ReconciliationRun (+ discrepancy detail)
│   │   └── xml_field_mapping.py          # NEW: XmlFieldMapping + XmlFieldMappingVersion
│   ├── services/
│   │   ├── legacy_shape_service.py       # NEW: capture + drift detection (FR-001/FR-013)
│   │   ├── view_definition_service.py    # NEW: join-graph validation, versioning (FR-002/003/004/007)
│   │   ├── ddl_generator.py              # NEW: builds CREATE/ALTER VIEW SQL from a version (FR-006)
│   │   ├── reconciliation_engine.py      # NEW: keyed row/column comparison (FR-009/FR-014)
│   │   └── xml_lookup_service.py         # NEW: XML field extraction via pushdown query (FR-011/012)
│   └── connectors/
│       └── mssql.py                      # REUSED as-is (list_tables already includes views)
└── tests/
    ├── unit/          # ddl_generator, join-graph validation, reconciliation comparison logic
    ├── integration/   # against docker-compose mssql: old-table fixture, 5-table fixture, xml-table fixture
    └── contract/      # new API routes

frontend/
├── src/
│   ├── components/canvas/
│   │   └── JoinGraphCanvas.tsx   # NEW: multi-source-table nodes + join edges, reuses
│   │                              # MappingCanvas's column-link interaction for the
│   │                              # final old-column -> source-expression mapping
│   ├── pages/
│   │   ├── ViewDefinitionEditor.tsx   # NEW
│   │   ├── ViewPreviewResults.tsx     # NEW
│   │   ├── ReconciliationResults.tsx  # NEW
│   │   └── XmlLookupPanel.tsx         # NEW
│   └── services/api.ts                # extended with the new endpoints
└── tests/
    ├── unit/    # JoinGraphCanvas edge creation/removal
    └── e2e/     # build -> preview -> deploy -> reconcile -> xml-lookup golden path
```

**Structure Decision**: Extends the existing 001 web-application layout in place (same
`backend/` + `frontend/` split, same reason: backend owns all SQL/DDL, frontend owns only
the canvas and result views). No new top-level project or service is introduced.

## Complexity Tracking

*No constitution violations — table intentionally omitted.*

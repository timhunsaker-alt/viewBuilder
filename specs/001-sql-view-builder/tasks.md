---

description: "Task list for viewBuilder: Visual SQL Server View/Mapping Builder"

---

# Tasks: Visual SQL Server View/Mapping Builder

**Input**: Design documents from `/specs/001-sql-view-builder/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included and REQUIRED for mapping/enum-translation/retirement/execution logic per
Constitution Principle V (Test-First for Migration Logic, NON-NEGOTIABLE). Lighter CRUD (plain
connection-config storage) still gets unit coverage but does not require a pre-written failing
contract test if it has no business logic beyond persistence.

**Organization**: Tasks are grouped by user story (spec.md priorities: US1, US2, US3 = P1;
US4, US5 = P2) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Include exact file paths in descriptions

## Path Conventions (Web app — see plan.md Project Structure)

- Backend: `backend/src/`, `backend/tests/`
- Frontend: `frontend/src/`, `frontend/tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create `backend/` and `frontend/` directory skeletons per plan.md Project Structure
      (`backend/src/{api,models,services,db,connectors}`, `backend/tests/{unit,integration,contract}`,
      `frontend/src/{components/canvas,components/shared,pages,services}`, `frontend/tests/{unit,e2e}`)
- [X] T002 Initialize backend Python project in `backend/` — `pyproject.toml`/`requirements.txt`
      with FastAPI, SQLAlchemy 2.x, pyodbc, Pydantic v2, Alembic, pytest, uvicorn
- [X] T003 [P] Initialize frontend project in `frontend/` — Vite + React 18 + TypeScript,
      `@xyflow/react`, TanStack Query, Vitest, React Testing Library, Playwright
- [X] T004 [P] Configure backend linting/formatting (ruff + black) in `backend/pyproject.toml`
- [X] T005 [P] Configure frontend linting/formatting (Biome, matching this workspace's other
      React projects) in `frontend/biome.json`
- [X] T006 [P] Write `backend/docker/docker-compose.yml` bringing up MS SQL Server (
      `mcr.microsoft.com/mssql/server`) and Postgres 16, per research.md §2/§4
- [X] T007 [P] Write `backend/docker/mssql-init/seed.sql` creating sample legacy-shaped tables:
      one plain table, one with an enum-coded status column, and one legacy
      retirement-reason table using enum codes (used by US2/US3 tests and quickstart.md)

**Checkpoint**: Repo skeleton, tooling, and local infra scripts exist; nothing runs yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T008 Configure metadata-store SQLAlchemy engine/session in `backend/src/db/session.py`
      and initialize Alembic in `backend/db/alembic/` pointed at Postgres (data-model.md)
- [ ] T009 [P] Implement `connection_config` SQLAlchemy model in
      `backend/src/models/connection_config.py` (data-model.md §connection_config) and its
      Alembic migration
- [ ] T010 [P] Implement `mapping_definition` + `mapping_version` SQLAlchemy models in
      `backend/src/models/mapping.py` and their Alembic migration (data-model.md
      §mapping_definition, §mapping_version)
- [ ] T011 [P] Implement `enum_translation_table` + `enum_translation_version` SQLAlchemy
      models in `backend/src/models/enum_translation.py` and their Alembic migration
      (data-model.md §enum_translation_table, §enum_translation_version)
- [ ] T012 [P] Implement `run_log_entry` SQLAlchemy model in `backend/src/models/run_log.py`
      and its Alembic migration (data-model.md §run_log_entry)
- [ ] T013 Implement MS SQL Server connector in `backend/src/connectors/mssql.py` —
      environment-tagged connection resolution (dev/test/prod), `credential_ref` lookup
      (opaque, never returns raw secret — Constitution Principle VI), and a schema-introspection
      helper (`list_tables`, `get_columns`) via SQLAlchemy `Inspector` (research.md §1)
- [ ] T014 Implement FastAPI app skeleton with versioned router mount at `/api/v1` in
      `backend/src/api/main.py`, plus the shared error-response shape (`{"error": {"code",
      "message", "details"}}`) from contracts/api.md
- [ ] T015 [P] Configure structured logging + error-handling middleware in
      `backend/src/api/middleware.py`
- [ ] T016 [P] Configure frontend typed API client scaffold in `frontend/src/services/api.ts`
      (base URL, error-shape parsing matching contracts/api.md) and TanStack Query provider
      setup in `frontend/src/main.tsx`

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Map a legacy table to a new table visually (Priority: P1) 🎯 MVP

**Goal**: Operator selects a legacy source table, drags column-to-column links to a target
table/view on a visual canvas, and saves/reopens a named, versioned mapping definition.

**Independent Test**: Connect to the seeded test SQL Server, select a source table, draw at
least one column link, save the mapping, reopen it, and confirm the same links are present.

### Tests for User Story 1 ⚠️

- [ ] T017 [P] [US1] Contract test `GET /connections/{id}/schema` in
      `backend/tests/contract/test_connections_schema.py` (against docker-compose mssql fixture)
- [ ] T018 [P] [US1] Contract test `POST /mappings` and `POST /mappings/{id}/versions` in
      `backend/tests/contract/test_mappings_crud.py`
- [ ] T019 [P] [US1] Unit test: mapping-version immutability (editing creates a new version,
      never mutates an existing one — Constitution Principle II) in
      `backend/tests/unit/test_mapping_versioning.py`
- [ ] T020 [P] [US1] Integration test: full save→reopen round trip against seeded mssql fixture
      in `backend/tests/integration/test_mapping_roundtrip.py`
- [ ] T021 [P] [US1] Frontend unit test for canvas link creation/removal in
      `frontend/tests/unit/canvas.test.tsx`

### Implementation for User Story 1

- [ ] T022 [US1] Implement connection CRUD service in
      `backend/src/services/connection_service.py` (create/list, never returns
      `credential_ref` — depends on T009, T013)
- [ ] T023 [US1] Implement `GET/POST /connections` and `GET /connections/{id}/schema` routes in
      `backend/src/api/connections.py` (depends on T022)
- [ ] T024 [US1] Implement mapping service in `backend/src/services/mapping_service.py` —
      create mapping definition + first version, save edit as new version, list versions
      (depends on T010)
- [ ] T025 [US1] Implement `POST /mappings`, `GET /mappings`, `GET /mappings/{id}`,
      `GET /mappings/{id}/versions`, `POST /mappings/{id}/versions` routes in
      `backend/src/api/mappings.py` (depends on T024)
- [ ] T026 [US1] Add mapping validation (source/target connection role compatibility, no
      dangling column references) in `backend/src/services/mapping_service.py`
- [ ] T027 [P] [US1] Build table/column picker page in `frontend/src/pages/TablePicker.tsx`
      (calls `GET /connections`, `GET /connections/{id}/schema`)
- [ ] T028 [P] [US1] Build React Flow mapping canvas component in
      `frontend/src/components/canvas/MappingCanvas.tsx` — source/target columns as nodes,
      drag-drawn links as edges, remove/redraw support (FR-003)
- [ ] T029 [US1] Build mapping editor page wiring TablePicker + MappingCanvas + save/version
      history in `frontend/src/pages/MappingEditor.tsx` (depends on T027, T028)
- [ ] T030 [US1] Add logging for mapping create/version-save operations in
      `backend/src/services/mapping_service.py`

**Checkpoint**: User Story 1 is fully functional and independently testable/demoable.

---

## Phase 4: User Story 2 - Translate enum-coded columns to their real values (Priority: P1)

**Goal**: While mapping an enum-coded source column, the user attaches a versioned
enum-translation table so dry-run/execute produce translated values, and unmapped codes are
flagged rather than guessed.

**Independent Test**: Map a known enum-coded column, attach a translation table with a few
entries, dry-run, and confirm the preview shows translated values plus a flagged count for any
missing code.

### Tests for User Story 2 ⚠️

- [ ] T031 [P] [US2] Contract test `POST /enum-translations` and
      `POST /enum-translations/{id}/versions` in
      `backend/tests/contract/test_enum_translations_crud.py`
- [ ] T032 [P] [US2] Unit test: enum translation applies known codes and flags unknown codes
      without defaulting/guessing (Constitution Principle III, FR-008) in
      `backend/tests/unit/test_enum_translation.py`
- [ ] T033 [P] [US2] Unit test: translation-table version uniqueness of codes within a version
      in `backend/tests/unit/test_enum_translation.py`
- [ ] T034 [P] [US2] Integration test against seeded mssql fixture: mapping with an attached
      enum-translation table dry-runs to translated sample rows and a correct
      `untranslatable_rows_flagged` count in `backend/tests/integration/test_enum_dry_run.py`

### Implementation for User Story 2

- [ ] T035 [US2] Implement enum-translation service in
      `backend/src/services/enum_translation_service.py` — create table + first version, save
      edit as new version, unique-code validation (depends on T011)
- [ ] T036 [US2] Implement `POST /enum-translations`, `GET /enum-translations`,
      `GET /enum-translations/{id}`, `POST /enum-translations/{id}/versions` routes in
      `backend/src/api/enum_translations.py` (depends on T035)
- [ ] T037 [US2] Extend `column_links` handling in mapping_service.py to accept an optional
      `enum_translation_version_id` per link, validating it was attached to that source column
      (depends on T024, T035)
- [ ] T038 [US2] Implement the translation-application step of the mapping engine in
      `backend/src/services/mapping_engine.py` — given a row and a mapping version, apply
      enum translations and collect untranslatable rows (depends on T037)
- [ ] T039 [P] [US2] Build enum-translation-table editor UI (create/edit entries, versioned) in
      `frontend/src/pages/EnumTranslationEditor.tsx`
- [ ] T040 [US2] Wire enum-column detection + translation-table attach UI into
      `frontend/src/pages/MappingEditor.tsx` (depends on T028, T039)

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Mark a row retired with a full audit trail (Priority: P1)

**Goal**: Running a retirement mapping writes a new retirement-audit record (identity,
translated reason, timestamp, mapping version) into the target database without ever mutating
or deleting the source row.

**Independent Test**: Run a retirement mapping against a source row with a known
retirement-status code; confirm the source row is byte-for-byte unchanged and a correct new
audit row exists.

### Tests for User Story 3 ⚠️

- [ ] T041 [P] [US3] Unit test: retirement write path never issues UPDATE/DELETE against the
      source table (Constitution Principle IV) in
      `backend/tests/unit/test_retirement_writer.py`
- [ ] T042 [P] [US3] Unit test: duplicate-retirement protection — re-running over an
      already-retired row does not create a second audit record (FR-011) in
      `backend/tests/unit/test_retirement_writer.py`
- [ ] T043 [P] [US3] Integration test against seeded mssql fixture: execute a retirement
      mapping, assert source row unchanged and audit row has correct identity/reason/timestamp/
      mapping_version in `backend/tests/integration/test_retirement_execute.py`

### Implementation for User Story 3

- [ ] T044 [US3] Add `retirement_config` (status_column, retired_value_codes,
      reason_column, row_identity_column, audit_binding) to mapping_version create/save in
      `backend/src/services/mapping_service.py` (depends on T024, data-model.md
      §retirement_audit_binding)
- [ ] T045 [US3] Implement retirement writer in `backend/src/services/retirement_writer.py` —
      reads source rows matching `retired_value_codes`, translates reason via attached enum
      table (depends on T038), checks target audit table for existing identity match before
      writing (dedup, FR-011), inserts new audit rows only — never touches the source table
      (depends on T013, T038)
- [ ] T046 [P] [US3] Build retirement-mapping configuration UI (status column, retired codes,
      audit-table binding fields) in `frontend/src/pages/RetirementConfig.tsx`

**Checkpoint**: User Stories 1, 2, AND 3 all work independently — this is the full "safe core"
of the tool per the constitution.

---

## Phase 6: User Story 4 - Preview a mapping with dry-run before touching real data (Priority: P2)

**Goal**: Any saved mapping (column mapping or retirement) can be run in dry-run mode, reporting
counts and sample rows with zero writes to target or retirement-audit tables.

**Independent Test**: Dry-run a saved mapping against a known small source table; confirm
reported counts/sample rows match manual inspection and that no rows were written anywhere.

### Tests for User Story 4 ⚠️

- [ ] T047 [P] [US4] Contract test `POST /mappings/{id}/dry-run` in
      `backend/tests/contract/test_dry_run.py`
- [ ] T048 [P] [US4] Integration test: dry-run against seeded mssql fixture writes zero rows to
      target/audit tables and returns correct counts + sample rows (US4 AC1-AC3) in
      `backend/tests/integration/test_dry_run_no_writes.py`

### Implementation for User Story 4

- [ ] T049 [US4] Implement dry-run orchestration in
      `backend/src/services/run_orchestrator.py` — reads source, applies mapping_engine
      (T038) and retirement_writer in preview mode (no writes), builds counts + capped sample
      rows, writes a `run_log_entry` with `mode=dry_run` (depends on T038, T045, T012)
- [ ] T050 [US4] Implement `POST /mappings/{id}/dry-run` route in
      `backend/src/api/runs.py` (depends on T049)
- [ ] T051 [P] [US4] Build dry-run results view (counts, sample rows, flagged
      untranslatable rows) in `frontend/src/pages/DryRunResults.tsx`
- [ ] T052 [US4] Wire "Run Dry Run" action from MappingEditor into DryRunResults (depends on
      T029, T051)

**Checkpoint**: All P1 stories plus dry-run preview work independently.

---

## Phase 7: User Story 5 - Execute a mapping and get an auditable run log (Priority: P2)

**Goal**: Execute a dry-run-reviewed mapping for real, performing the actual writes, with a
production-confirmation gate and a full run-log entry.

**Independent Test**: Execute a mapping against the test database; confirm target/audit tables
contain expected rows and a run-log entry exists with matching counts, mapping version, and
timestamp.

### Tests for User Story 5 ⚠️

- [ ] T053 [P] [US5] Contract test `POST /mappings/{id}/execute` including the
      `production_confirmation_required` 409 case (FR-016) in
      `backend/tests/contract/test_execute.py`
- [ ] T054 [P] [US5] Integration test: execute against seeded mssql fixture writes expected
      target/audit rows and a matching completed `run_log_entry` in
      `backend/tests/integration/test_execute_run.py`
- [ ] T055 [P] [US5] Integration test: pre-flight schema check blocks execution with no partial
      writes when a mapped column/table is missing or type-incompatible (FR-015) in
      `backend/tests/integration/test_execute_schema_drift.py`
- [ ] T056 [P] [US5] Unit test: untranslatable rows during execute are skipped and counted, not
      written with a guessed/default value (FR-008, US5 AC3) in
      `backend/tests/unit/test_execute_untranslatable.py`
- [ ] T057 [P] [US5] Contract test `GET /runs` and `GET /runs/{id}` filtering in
      `backend/tests/contract/test_runs_list.py`

### Implementation for User Story 5

- [ ] T058 [US5] Implement pre-flight schema-drift check (re-introspect source/target against
      mapping version's referenced tables/columns) in
      `backend/src/services/run_orchestrator.py` (depends on T013, T049)
- [ ] T059 [US5] Implement execute orchestration — real reads/translations/writes to target and
      retirement-audit tables, production-confirmation gate check, completed `run_log_entry`
      write in `backend/src/services/run_orchestrator.py` (depends on T049, T058)
- [ ] T060 [US5] Implement `POST /mappings/{id}/execute` route with `confirm_production` body
      handling and 409 response in `backend/src/api/runs.py` (depends on T059)
- [ ] T061 [US5] Implement `GET /runs`, `GET /runs/{id}` routes (filter by
      `mapping_definition_id`, `mode`) in `backend/src/api/runs.py` (depends on T012)
- [ ] T062 [P] [US5] Build run history page (list + detail view of run_log_entry) in
      `frontend/src/pages/RunHistory.tsx`
- [ ] T063 [US5] Wire "Execute" action (with production-confirmation prompt) from
      DryRunResults into the execute flow (depends on T051, T062)

**Checkpoint**: All user stories (US1-US5) are independently functional — full spec delivered.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T064 [P] Playwright end-to-end test covering the full quickstart.md golden path (pick
      table → link columns → attach enum translation → save → dry-run → execute → retire) in
      `frontend/tests/e2e/golden-path.spec.ts`
- [ ] T065 [P] Add environment-tag production-confirmation UI safeguard (distinct visual
      warning + confirmation dialog) in `frontend/src/components/shared/ProductionGuard.tsx`
- [ ] T066 [P] README with setup/run instructions at repository root, linking to
      `specs/001-sql-view-builder/quickstart.md`
- [ ] T067 Run full `quickstart.md` validation end-to-end and fix any drift between docs and
      actual behavior
- [ ] T068 [P] Add structured audit logging (operator, action, mapping/translation version) for
      every mutating endpoint in `backend/src/api/middleware.py`
- [ ] T069 Review all endpoints against contracts/api.md for drift; regenerate/update OpenAPI
      docs if any diverged

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational only
- **US2 (Phase 4)**: Depends on Foundational; extends US1's mapping model/UI (T037, T040
  build on T024/T028) but is independently testable via its own dry-run-less unit/integration
  tests
- **US3 (Phase 5)**: Depends on Foundational; extends US1's mapping model (T044 builds on
  T024) and reuses US2's translation-application step (T045 depends on T038)
- **US4 (Phase 6)**: Depends on US2 and US3 implementation work being available to preview
  (T049 depends on T038, T045) — dry-run has nothing to preview without them
- **US5 (Phase 7)**: Depends on US4 (execute reuses/extends the dry-run orchestration path,
  T059 depends on T049)
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories — pure column-mapping CRUD + canvas
- **US2 (P1)**: Builds on US1's mapping model but is independently testable (enum translation
  unit tests don't require the canvas)
- **US3 (P1)**: Builds on US1's mapping model and US2's translation step, independently
  testable via its own retirement-specific tests
- **US4 (P2)**: Requires US1-US3's engine pieces to exist to have something to preview
- **US5 (P2)**: Requires US4's orchestration to extend into real writes

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Constitution Principle V)
- Models before services; services before endpoints; backend before dependent frontend wiring
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T003-T007)
- All Foundational model tasks marked [P] can run in parallel (T009-T012)
- All tests for a given user story marked [P] can run in parallel
- Frontend page/component tasks marked [P] can run in parallel with sibling backend tasks once
  the relevant contract is stable

---

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "Contract test POST /enum-translations in backend/tests/contract/test_enum_translations_crud.py"
Task: "Unit test enum translation known/unknown codes in backend/tests/unit/test_enum_translation.py"
Task: "Unit test translation-version code uniqueness in backend/tests/unit/test_enum_translation.py"
Task: "Integration test enum dry-run against seeded mssql in backend/tests/integration/test_enum_dry_run.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Save/reopen a mapping independently
5. Demo the canvas mapping flow

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → validate → demo (basic mapping canvas)
3. US2 → validate → demo (enum translation)
4. US3 → validate → demo (retirement audit) — **this completes the full "safe core" the
   constitution treats as non-negotiable**
5. US4 → validate → demo (dry-run preview)
6. US5 → validate → demo (real execution + run log) — full spec delivered
7. Polish

### Parallel Team Strategy

With multiple developers, after Foundational completes: one developer on US1 (canvas), one on
US2 (enum translation service — mostly backend, independently unit-testable), one on US3
(retirement writer — mostly backend). US4/US5 should wait for US1-US3's engine pieces since
they orchestrate on top of them.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Tests are included per Constitution Principle V — write and confirm failing before
  implementing the corresponding task
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- No task performs a destructive operation (UPDATE/DELETE/DROP) against a legacy source table
  — this is enforced by design (US3 tests) and must not be introduced later

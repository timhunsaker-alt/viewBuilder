---

description: "Task list for legacy-compat-view: Legacy-Shape Compatibility View & Reconciliation"

---

# Tasks: Legacy-Shape Compatibility View & Reconciliation

**Input**: Design documents from `/specs/002-legacy-compat-view/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included and REQUIRED for DDL-generation, join-graph validation, reconciliation-
comparison, and XML-extraction logic per Constitution Principle V (Test-First for
Migration Logic, generalized in plan.md's Constitution Check to cover this feature's
DDL/comparison logic the same way).

**Organization**: Tasks are grouped by user story (spec.md priorities: US1, US2, US3 = P1;
US4 = P2) to enable independent implementation and testing of each story. This feature
extends the existing 001-sql-view-builder codebase in place — task file paths are under
the same `backend/` and `frontend/` trees.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)
- Include exact file paths in descriptions

## Path Conventions (extends 001's web-app layout — see plan.md Project Structure)

- Backend: `backend/src/`, `backend/tests/`
- Frontend: `frontend/src/`, `frontend/tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Extend the existing local fixtures with what this feature needs; no new
project scaffolding required since this builds on 001's backend/frontend in place.

- [X] T001 Extend `backend/docker/mssql-init/seed.sql` (or add a new
      `backend/docker/mssql-init/seed_legacy_compat.sql` sourced by the same init flow)
      with: an old wide table (`dbo.legacy_loan_application`, ~15-20 columns), a 5-table
      normalized replacement schema (`dbo.loan_application`, `dbo.loan_applicant`,
      `dbo.loan_collateral`, `dbo.loan_underwriting`, `dbo.loan_document_ref`, joined by a
      shared `application_id`), and an XML document table (`dbo.legacy_application_xml`
      with `application_id` + an `xml` payload column) with sample documents — including
      at least one deliberately missing a field also missing from the normalized schema
      (per quickstart.md)
- [X] T002 [P] Ensure the new seed objects are dropped in reverse-dependency order at the
      top of the seed script, matching the idempotent-redeploy fix already applied to
      001's seed data

**Checkpoint**: Local/deployed fixtures exist for every new user story to build against.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be
implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Implement `legacy_shape_capture` SQLAlchemy model in
      `backend/src/models/legacy_shape.py` and its Alembic migration (data-model.md
      §legacy_shape_capture)
- [X] T004 [P] Implement `view_definition` + `view_definition_version` SQLAlchemy models
      in `backend/src/models/view_definition.py` and their Alembic migration (data-model.md
      §view_definition, §view_definition_version)
- [X] T005 [P] Implement `view_deployment_log` SQLAlchemy model in
      `backend/src/models/deployment_log.py` and its Alembic migration (data-model.md
      §view_deployment_log)
- [X] T006 [P] Implement `reconciliation_run` SQLAlchemy model in
      `backend/src/models/reconciliation.py` and its Alembic migration (data-model.md
      §reconciliation_run)
- [X] T007 [P] Implement `xml_field_mapping` + `xml_field_mapping_version` SQLAlchemy
      models in `backend/src/models/xml_field_mapping.py` and their Alembic migration
      (data-model.md §xml_field_mapping, §xml_field_mapping_version)
- [X] T008 Extend `backend/src/api/main.py` to mount the new routers (`legacy_shapes`,
      `view_definitions`, `reconciliation`, `xml_mappings`) under `/api/v1`, reusing the
      existing error-response shape and audit-logging middleware from 001
- [X] T009 [P] Add the new error codes (`name_collision`, `not_deployed`, and reused
      `schema_mismatch`/`mapping_invalid`/`connection_unreachable`/
      `production_confirmation_required`) to `backend/src/api/errors.py` (or wherever
      001's `ApiError` catalogue lives) per contracts/api.md
- [X] T010 [P] Configure frontend typed API client additions in
      `frontend/src/services/api.ts` for the new endpoints (legacy-shapes,
      view-definitions, reconciliation, xml-field-mappings)

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Build a compatibility view that reconstructs the old table's exact shape (Priority: P1) 🎯 MVP

**Goal**: Capture the old table's shape, configure a join graph + column mapping over the
new normalized tables, preview the generated view, and deploy it as a real SQL VIEW with
matching column list/order.

**Independent Test**: Point the tool at the seeded old wide table and its 5-table
replacement, build the view definition, preview it, deploy it, and confirm the deployed
view's introspected columns exactly match the old table's, in order.

### Tests for User Story 1 ⚠️

- [X] T011 [P] [US1] Contract test `POST /legacy-shapes` and `GET /legacy-shapes/{id}/drift`
      in `backend/tests/contract/test_legacy_shapes.py` (against docker-compose mssql
      fixture)
- [X] T012 [P] [US1] Contract test `POST /view-definitions` rejecting incomplete
      `column_mappings` (FR-004) and unreachable `join_graph` tables (FR-002) in
      `backend/tests/contract/test_view_definitions_crud.py`
- [X] T013 [P] [US1] Contract test `POST /view-definitions` rejecting a `name` that
      collides with the legacy shape's own `table_name` in
      `backend/tests/contract/test_view_definitions_crud.py`
- [X] T014 [P] [US1] Unit test: `ddl_generator` produces a `CREATE OR ALTER VIEW` whose
      column list/order exactly matches a given `legacy_shape_capture.columns` for a
      variety of join-graph shapes (star join, chain join) in
      `backend/tests/unit/test_ddl_generator.py`
- [X] T015 [P] [US1] Unit test: join-graph reachability validation rejects an orphan table
      in `backend/tests/unit/test_join_graph_validation.py`
- [X] T016 [P] [US1] Contract test `POST /view-definitions/{id}/preview` returns generated
      SQL + sample rows and performs zero DDL (verify no new object exists after) in
      `backend/tests/contract/test_view_preview.py`
- [X] T017 [P] [US1] Integration test against seeded mssql fixture: full
      capture → define → preview → deploy round trip, asserting the deployed view's
      introspected columns match the legacy shape exactly, in
      `backend/tests/integration/test_view_deploy_roundtrip.py`
- [X] T018 [P] [US1] Frontend unit test for `JoinGraphCanvas` edge creation/removal in
      `frontend/tests/unit/join_graph_canvas.test.tsx`

### Implementation for User Story 1

- [X] T019 [US1] Implement `legacy_shape_service` in
      `backend/src/services/legacy_shape_service.py` — capture (introspect + store) and
      drift detection (re-introspect vs. stored, FR-001/FR-013; depends on T003)
- [X] T020 [US1] Implement `POST /legacy-shapes`, `GET /legacy-shapes`,
      `GET /legacy-shapes/{id}`, `GET /legacy-shapes/{id}/drift` routes in
      `backend/src/api/legacy_shapes.py` (depends on T019)
- [X] T021 [US1] Implement join-graph reachability validation in
      `backend/src/services/view_definition_service.py` (FR-002; depends on T004)
- [X] T022 [US1] Implement column-mapping completeness validation (every legacy-shape
      column covered, FR-004) in `backend/src/services/view_definition_service.py`
      (depends on T021)
- [X] T023 [US1] Implement `ddl_generator` in `backend/src/services/ddl_generator.py` —
      builds the `CREATE OR ALTER VIEW` SQL from a join graph + column mapping, preserving
      legacy-shape column order (FR-006; depends on T022)
- [X] T024 [US1] Implement `POST /view-definitions`, `GET /view-definitions`,
      `GET /view-definitions/{id}`, `GET /view-definitions/{id}/versions`,
      `POST /view-definitions/{id}/versions` routes in
      `backend/src/api/view_definitions.py` (depends on T023)
- [X] T025 [US1] Implement `POST /view-definitions/{id}/preview` — re-check drift, generate
      SQL, run it as a read-only `SELECT` for a sample, log a `view_deployment_log` row
      with `mode=preview` (FR-005; depends on T020, T023)
- [X] T026 [US1] Implement `POST /view-definitions/{id}/deploy` — re-check drift, execute
      the generated DDL for real, log a `view_deployment_log` row with `mode=deploy`
      (FR-006/FR-008; depends on T025)
- [X] T027 [P] [US1] Build `JoinGraphCanvas.tsx` in
      `frontend/src/components/canvas/JoinGraphCanvas.tsx` — multi-table nodes with
      draggable join edges (research.md §4)
- [X] T028 [US1] Build `ViewDefinitionEditor.tsx` in `frontend/src/pages/` wiring legacy
      shape selection + `JoinGraphCanvas` + the reused column-link canvas interaction for
      the final old-column → source mapping (depends on T027)
- [X] T029 [P] [US1] Build `ViewPreviewResults.tsx` in `frontend/src/pages/` showing
      generated SQL + sample rows

**Checkpoint**: User Story 1 is fully functional and independently testable/demoable —
this is the MVP.

---

## Phase 4: User Story 2 - Version and safely redeploy the view definition (Priority: P1)

**Goal**: Editing and redeploying a view definition creates a new immutable version;
redeploys that change the column shape are explicitly flagged before/after deploy.

**Independent Test**: Deploy a view, edit a mapping, redeploy, and confirm the previous
version's full definition (including its exact generated SQL) is still retrievable, and
that a column-shape-changing redeploy is flagged in its `column_diff`.

### Tests for User Story 2 ⚠️

- [X] T030 [P] [US2] Unit test: view-definition-version immutability (editing creates a
      new version, never mutates an existing one) in
      `backend/tests/unit/test_view_versioning.py`
- [X] T031 [P] [US2] Contract test: version history (`GET /view-definitions/{id}/versions`)
      returns each version's exact `generated_sql` in
      `backend/tests/contract/test_view_definitions_crud.py`
- [X] T032 [P] [US2] Unit test: `column_diff` computation correctly identifies added/
      removed/reordered columns between two versions' generated shapes in
      `backend/tests/unit/test_column_diff.py`

### Implementation for User Story 2

- [X] T033 [US2] Extend `view_definition_service` to save an edit as a new version without
      mutating prior versions (depends on T022)
- [X] T034 [US2] Implement `column_diff` computation in
      `backend/src/services/view_definition_service.py`, invoked by
      `POST /view-definitions/{id}/deploy` when a prior version was already live (US2 AC3;
      depends on T026, T032)
- [X] T035 [P] [US2] Surface version history + `column_diff` highlighting in
      `ViewDefinitionEditor.tsx` (depends on T028, T034)

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Reconcile the view against the still-live old table (Priority: P1)

**Goal**: Compare a deployed view's live output against the old table, keyed by an
identity column, reporting row-level and column-level discrepancies.

**Independent Test**: Reconcile a cleanly-deployed view (expect zero discrepancies), then
redeploy with a deliberately wrong column mapping and reconcile again (expect exactly that
discrepancy flagged, nothing else).

### Tests for User Story 3 ⚠️

- [X] T036 [P] [US3] Unit test: reconciliation comparison logic correctly computes
      matched/old-only/view-only counts and per-column mismatch detail from two given row
      sets in `backend/tests/unit/test_reconciliation_engine.py`
- [X] T037 [P] [US3] Unit test: row-inflation is flagged distinctly from an ordinary
      mismatch when a join produces >1 view row per old-table identity (FR-014) in
      `backend/tests/unit/test_reconciliation_engine.py`
- [X] T038 [P] [US3] Contract test `POST /view-definitions/{id}/reconcile` returns
      `not_deployed` for a version with no successful deploy log in
      `backend/tests/contract/test_reconciliation.py`
- [X] T039 [P] [US3] Integration test against seeded mssql fixture: reconcile a cleanly
      deployed view (zero discrepancies), then a deliberately-wrong-mapping redeploy
      (discrepancy correctly flagged and nothing else) in
      `backend/tests/integration/test_reconciliation_live.py`

### Implementation for User Story 3

- [X] T040 [US3] Implement `reconciliation_engine` in
      `backend/src/services/reconciliation_engine.py` — keyed, chunked row/column compare
      per research.md §2 (FR-009/FR-014; depends on T004)
- [X] T041 [US3] Implement `POST /view-definitions/{id}/reconcile`,
      `GET /view-definitions/{id}/reconciliations`, `GET /reconciliations/{id}` routes in
      `backend/src/api/reconciliation.py` (depends on T040)
- [X] T042 [P] [US3] Build `ReconciliationResults.tsx` in `frontend/src/pages/` — counts
      summary + per-row/column discrepancy detail view

**Checkpoint**: User Stories 1, 2, AND 3 all work independently — the full "verify the
migration is actually correct" loop is complete.

---

## Phase 6: User Story 4 - Fall back to legacy XML when the new schema is missing data (Priority: P2)

**Goal**: For a reconciliation-flagged column, configure and run a lookup into the legacy
XML document store, distinguishing found/field-missing/document-not-found.

**Independent Test**: Configure an XML field mapping for a column known to be present in
sample XML, run the lookup (expect `found`); configure one for a column deliberately
missing from the sample XML too (expect `field_missing`); look up an identity with no XML
document at all (expect `document_not_found`).

### Tests for User Story 4 ⚠️

- [ ] T043 [P] [US4] Unit test: pushdown lookup query correctly distinguishes all three
      outcomes given controlled fixture data in
      `backend/tests/unit/test_xml_lookup_service.py`
- [ ] T044 [P] [US4] Contract test `POST /xml-field-mappings/{id}/lookup` returns
      `mapping_invalid` when no `field_paths` entry exists for the requested column in
      `backend/tests/contract/test_xml_field_mappings.py`
- [ ] T045 [P] [US4] Integration test against seeded mssql fixture (using the sample XML
      documents from T001): all three outcomes reproduced against real data in
      `backend/tests/integration/test_xml_lookup_live.py`

### Implementation for User Story 4

- [ ] T046 [US4] Implement `xml_lookup_service` in
      `backend/src/services/xml_lookup_service.py` — builds and runs the `.value()`/
      `EXISTS` pushdown query per research.md §1 (FR-011/FR-012; depends on T007)
- [ ] T047 [US4] Implement `POST /xml-field-mappings`, `GET /xml-field-mappings`,
      `GET /xml-field-mappings/{id}`, `POST /xml-field-mappings/{id}/versions`,
      `POST /xml-field-mappings/{id}/lookup` routes in
      `backend/src/api/xml_mappings.py` (depends on T046)
- [ ] T048 [P] [US4] Build `XmlLookupPanel.tsx` in `frontend/src/pages/` — field-path
      configuration + lookup trigger + three-outcome result display, reachable from a
      flagged row in `ReconciliationResults.tsx` (depends on T042)

**Checkpoint**: All user stories (US1-US4) are independently functional — full spec
delivered.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T049 [P] Playwright end-to-end test covering the full quickstart.md golden path
      (capture shape → build join graph + column map → preview → deploy → reconcile →
      XML lookup) in `frontend/tests/e2e/legacy-compat-golden-path.spec.ts`
- [ ] T050 [P] Reuse `ProductionGuard.tsx` (from 001) to gate the **Deploy** action in
      `ViewDefinitionEditor.tsx` the same way it gates **Execute** in 001's
      `DryRunResults.tsx`
- [ ] T051 Update root `README.md` and `specs/002-legacy-compat-view/quickstart.md` after
      running the golden path end-to-end as far as this sandbox allows; fix any drift
      found
- [ ] T052 [P] Extend the existing audit-logging middleware
      (`backend/src/api/middleware.py`) to cover this feature's mutating endpoints
      (`POST /legacy-shapes`, `POST /view-definitions`, `.../versions`, `.../deploy`,
      `POST /xml-field-mappings`, `.../versions`)
- [ ] T053 Review all new endpoints against `contracts/api.md` for drift; fix any real
      code/doc mismatches found (same practice as 001's T069)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational only — this is the MVP
- **US2 (Phase 4)**: Depends on Foundational; extends US1's view-definition model (T033
  builds on T022) but is independently testable via its own versioning/diff unit tests
- **US3 (Phase 5)**: Depends on Foundational and on US1 having a deployable view to
  reconcile against (T041 depends on `view_deployment_log` existing, from US1's T026) —
  independently testable via its own comparison-logic unit tests without needing US2
- **US4 (Phase 6)**: Depends on Foundational; benefits from US3 existing (reconciliation
  is what surfaces columns worth looking up) but its own tests are self-contained against
  known fixture data, not literally requiring a prior reconciliation run
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories — the MVP
- **US2 (P1)**: Builds on US1's view-definition model but independently testable
- **US3 (P1)**: Requires US1's deploy capability to have something to reconcile against,
  but its comparison logic is independently unit-testable
- **US4 (P2)**: Conceptually follows from US3 (investigating a flagged discrepancy) but is
  independently testable against fixture data alone

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Constitution Principle V)
- Models before services; services before endpoints; backend before dependent frontend
  wiring
- Story complete before moving to next priority

### Parallel Opportunities

- All Foundational model tasks marked [P] can run in parallel (T003-T007, T009-T010)
- All tests for a given user story marked [P] can run in parallel
- Frontend page/component tasks marked [P] can run in parallel with sibling backend tasks
  once the relevant contract is stable

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Contract test POST /legacy-shapes in backend/tests/contract/test_legacy_shapes.py"
Task: "Unit test ddl_generator column order in backend/tests/unit/test_ddl_generator.py"
Task: "Unit test join-graph reachability in backend/tests/unit/test_join_graph_validation.py"
Task: "Contract test POST /view-definitions/{id}/preview in backend/tests/contract/test_view_preview.py"
Task: "Integration test view deploy roundtrip in backend/tests/integration/test_view_deploy_roundtrip.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Deploy a real view and confirm its shape matches the old table
5. Demo the join-graph + column-mapping canvas

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → validate → demo (deployable compatibility view — MVP!)
3. US2 → validate → demo (safe versioned redeploys)
4. US3 → validate → demo (reconciliation) — this is the "prove the migration is correct"
   payoff
5. US4 → validate → demo (XML fallback) — full spec delivered
6. Polish

### Parallel Team Strategy

With multiple developers, after Foundational completes: one developer on US1 (view
definition + DDL generation + canvas), one on US3 (reconciliation engine — mostly
backend, independently unit-testable against fixture row sets), one on US4 (XML lookup —
also mostly backend, independently testable). US2 is a light extension best done by
whoever finishes US1 first.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Tests are included per Constitution Principle V — write and confirm failing before
  implementing the corresponding task
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- No task ever issues UPDATE/DELETE/DROP against the old table, the new schema, or the
  XML document store — reconciliation and XML lookup are read-only by construction; this
  must not be introduced later

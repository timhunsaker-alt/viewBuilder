<!--
Sync Impact Report
- Version change: (none) → 1.0.0
- Modified principles: n/a (initial ratification)
- Added sections:
  - Core Principles: I. Reviewable, Reversible Migrations; II. Mapping Definitions as Versioned Data;
    III. Auditable Enum Translation; IV. Retirement Is Append-Only Audit, Never Silent Mutation;
    V. Test-First for Migration Logic (NON-NEGOTIABLE); VI. Backend/Frontend Separation of Concerns;
    VII. Environment Separation
  - Technology Constraints
  - Development Workflow & Quality Gates
  - Governance
- Removed sections: none (template placeholders only)
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (generic Constitution Check gate references this file; no edits needed)
  - ✅ .specify/templates/spec-template.md (no principle-specific mandatory sections to add)
  - ✅ .specify/templates/tasks-template.md (generic categories already accommodate migration/test/audit tasks)
  - ✅ CLAUDE.md (points to plan.md for stack details; no stale references)
- Follow-up TODOs: none
-->

# viewBuilder Constitution

## Core Principles

### I. Reviewable, Reversible Migrations
Every migration or view-build operation against a real SQL Server database MUST support a
dry-run mode that reports exactly what would change (rows read, rows written, enum
translations applied, retirements recorded) without writing anything. No migration MAY be
executed against a non-dev/test database without first being run in dry-run mode and reviewed
by a human. Every migration run MUST be logged with enough detail (source query, mapping
version, row counts, timestamp, operator) to be reconstructed or rolled back. Destructive
operations (drop, truncate, hard delete) against source/legacy tables are prohibited by
default; the tool only reads from legacy tables and writes to new tables/views.
Rationale: legacy MS SQL tables hold data of record that cannot be regenerated; a wrong
mapping run at full speed against production is the single most expensive failure mode this
tool can produce.

### II. Mapping Definitions as Versioned Data
The relationship between a source table/column and its target table/column — including any
enum-translation rule — MUST be expressed as structured, versioned configuration (e.g. JSON
files or DB-backed mapping records), never as inline/hardcoded logic in application code.
Mapping definitions MUST be independently reviewable (diffable) and MUST carry a version
identifier that is stamped onto every migration run that used them. Changing a mapping
definition MUST NOT silently change the behavior of a previously-executed, already-audited
migration run.
Rationale: the drag-and-drop canvas is a UI over data, not a code generator; keeping mappings
as data is what makes them visually editable, diffable, and safely re-runnable.

### III. Auditable Enum Translation
Enum-to-value translation tables MUST be explicit, table-driven lookups (source enum code →
target value), stored alongside mapping definitions, and versioned the same way. A source
enum code with no matching translation entry MUST cause the migration to fail loudly (or be
flagged in dry-run) rather than being coerced, defaulted, or silently dropped. Every executed
translation MUST be traceable after the fact to the exact lookup table version that produced
it.
Rationale: several legacy tables encode meaning as enums; a silent or lossy translation turns
a data-shape problem into a data-correctness problem that is far harder to detect later.

### IV. Retirement Is Append-Only Audit, Never Silent Mutation
Marking a row "retired" MUST never be implemented as an in-place update or delete of the
source/legacy record. Retirement MUST always produce a new record in an audit/history table
capturing at minimum: the retired row's identity, the retirement reason (translated from the
legacy enum-coded reason where applicable, per Principle III), the timestamp, and the
migration/mapping version that performed the retirement. The audit table's schema is
append-only from the application's perspective — no update or delete operations against it are
permitted outside of an explicit, documented administrative correction.
Rationale: retirement history is itself data of record (compliance/traceability); collapsing
it into a mutable status flag destroys the ability to answer "what happened and when."

### V. Test-First for Migration Logic (NON-NEGOTIABLE)
Any code that reads legacy tables, applies a mapping, translates enums, or writes
target/audit records MUST have automated tests written and failing before the implementation
is written, and those tests MUST pass before the code is considered done. Every enum
translation table and every mapping definition shipped MUST have a corresponding test
asserting its exact input→output behavior, including the failure case of an unmapped enum
code (Principle III). Bug fixes in migration logic MUST add a regression test that reproduces
the bug first.
Rationale: this is the highest-blast-radius code in the system; the cost of a missed edge
case is corrupted or lost data in someone else's production database.

### VI. Backend/Frontend Separation of Concerns
The FastAPI backend owns all SQL Server introspection, mapping validation, enum translation,
migration execution, and audit-record writing; it exposes this exclusively through a
versioned HTTP API. The React/TypeScript frontend owns only presentation and interaction for
the visual drag-and-drop mapping canvas and MUST NOT contain SQL, connection strings, or
migration-execution logic — it calls the backend API for schema discovery, mapping
CRUD/validation, dry-run previews, and migration execution. Raw database credentials are
never sent to or held by the frontend.
Rationale: keeping all data-touching logic server-side keeps the destructive-action surface
small, testable, and auditable in one place.

### VII. Environment Separation
The tool MUST distinguish target environments (at minimum: local/dev, test, and any
real/production SQL Server) via explicit configuration, never a hardcoded connection string.
Connecting to a database flagged as production MUST require an explicit, distinct
confirmation step beyond what dev/test connections require, and MUST default to dry-run mode.
Credentials for different environments MUST be stored and loaded separately (e.g. per-
environment secrets/config), never shared or interpolated from a single literal.
Rationale: this tool's entire job is to touch legacy databases; environment mix-ups are a
direct path to Principle I violations.

## Technology Constraints

Backend: Python (FastAPI) for schema introspection, mapping validation, enum translation, and
migration execution against MS SQL Server. Frontend: React with TypeScript for the visual
drag-and-drop mapping canvas. viewBuilder is an independent repository with its own history,
CI, and releases — it does not inherit or participate in any other project's dual-write or
branching conventions. Any cross-project reuse (e.g. shared mapping-definition schemas) MUST
be pulled in deliberately and documented, not assumed.

## Development Workflow & Quality Gates

All new features are specified via `/speckit-specify` and planned via `/speckit-plan` before
implementation. A pull request touching mapping, enum-translation, retirement, or migration
execution code MUST include or update the tests required by Principle V, and MUST include a
dry-run output example in the PR description when it changes migration behavior. Direct
commits to the default branch are disallowed; changes land via reviewed pull request.

## Governance

This constitution supersedes ad hoc practice for this repository. Amendments require: (1) a
documented rationale for the change, (2) a version bump per semantic versioning (MAJOR for
backward-incompatible principle removal/redefinition, MINOR for new/materially-expanded
principles or sections, PATCH for clarifications/wording), and (3) propagation of any
resulting changes to `.specify/templates/*` and agent guidance files in the same change. All
pull requests MUST be checked against this constitution before merge; any deviation must be
justified in the PR description or the PR MUST be revised to comply. Use `CLAUDE.md` (and the
current feature's `plan.md`) for day-to-day runtime development guidance.

**Version**: 1.0.0 | **Ratified**: 2026-09-09 | **Last Amended**: 2026-09-09

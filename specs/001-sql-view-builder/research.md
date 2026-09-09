# Phase 0 Research: Visual SQL Server View/Mapping Builder

All Technical Context items were resolvable from the spec, constitution, and the user-provided
tech-stack direction; no unresolved `NEEDS CLARIFICATION` markers remain.

## 1. SQL Server connectivity from Python

**Decision**: SQLAlchemy 2.x with the `mssql+pyodbc` dialect, using Microsoft's ODBC Driver 18
for SQL Server.

**Rationale**: pyodbc is the most mature, widely-used driver for MS SQL Server from Python and
integrates cleanly with SQLAlchemy's reflection API (`Inspector.get_columns`,
`get_table_names`), which directly serves the schema-introspection requirement (FR-001/FR-002).
SQLAlchemy's Core (not necessarily the ORM) is enough for building parameterized, dynamic
SELECT/INSERT statements against arbitrary legacy tables whose shape isn't known at
development time.

**Alternatives considered**: `pymssql` (simpler install, but less actively maintained and
weaker reflection support); raw `pyodbc` without SQLAlchemy (more control, but reimplements
reflection and parameterized-query-building that SQLAlchemy already provides safely — rejected
as unnecessary complexity per the constitution's implicit simplicity bias).

## 2. Application metadata store

**Decision**: PostgreSQL 16 for mapping definitions, enum-translation tables, and run logs.
Retirement audit records are written into the *target* SQL Server database itself (per
spec FR-009, the retirement audit table is a real table the migrated system will query), not
into the Postgres metadata store.

**Rationale**: Keeping the app's own versioned metadata (mappings, translations, run logs) in a
separate, standard relational store decouples the tool's operability from the legacy SQL
Server instances it touches — the tool must remain usable even if a given legacy source is
temporarily unreachable. Postgres was chosen over standardizing everything on SQL Server
because it is free of any licensing/connection-pool contention with the legacy instances being
migrated, and Alembic + SQLAlchemy tooling for it is simpler than juggling two different SQL
Server roles (metadata vs. legacy) through the same driver stack.

**Alternatives considered**: Using SQL Server for metadata too (rejected: unnecessarily
couples the tool's own operability to SQL Server licensing/availability, no functional
benefit); SQLite (rejected: multi-version mapping/translation history plus concurrent run logs
benefit from a real server-based RDBMS from day one, even for a single-operator tool, to avoid
a migration later).

## 3. Visual drag-and-drop mapping canvas

**Decision**: React Flow (`@xyflow/react`) for the node/edge canvas that renders source columns
and target columns as nodes and mapping links as edges.

**Rationale**: React Flow is purpose-built for exactly this interaction (draggable nodes,
user-drawn edges between named handles), has strong TypeScript support, and avoids building
custom SVG/canvas drag-link handling from scratch — directly serves FR-003 (draw/remove/redraw
links) with minimal custom code.

**Alternatives considered**: Hand-rolled SVG + custom drag logic (rejected: significant custom
code for a solved problem, conflicts with the "don't reinvent" simplicity bias); jsPlumb
(older, less TypeScript-idiomatic, weaker React integration than React Flow).

## 4. Enum translation & retirement-audit correctness testing

**Decision**: pytest with a docker-compose-provisioned MS SQL Server container (Microsoft's
official `mcr.microsoft.com/mssql/server` image) seeded via a SQL init script with
legacy-shaped sample tables (including enum-coded columns and a sample legacy
retirement-status table), so integration tests exercise the real dialect/driver path without
needing a real legacy database.

**Rationale**: Constitution Principle V requires test-first coverage for exactly this class of
logic, and Principle I requires this to be provably safe before touching real data — a
docker-compose fixture is the only way to get real SQL Server semantics (collations, enum-code
data types, transaction behavior) under CI without a live legacy connection.

**Alternatives considered**: Mocking the DB layer entirely (rejected: constitution explicitly
treats this as the highest-blast-radius code in the system; a mock could pass while a real
SQL Server quirk — e.g., NULL-vs-empty-string enum codes — breaks in production); SQLite
in-memory as a SQL Server stand-in (rejected: dialect differences, e.g., T-SQL specific
features used for schema introspection, make it an unreliable substitute).

## 5. Versioning model for mappings & translation tables

**Decision**: Each `MappingDefinition` and `EnumTranslationTable` is an immutable-version
append model: editing and saving creates a new `MappingVersion`/`EnumTranslationVersion` row
referencing its parent definition, rather than mutating the previous version's row. Every
`RunLogEntry` (dry-run or execute) stores the exact version id(s) it used.

**Rationale**: Directly implements Constitution Principle II ("changing a mapping definition
MUST NOT silently change the behavior of a previously-executed... run") and spec FR-004/FR-006.

**Alternatives considered**: Single mutable row + separate changelog/audit log (rejected:
makes "what version did this run actually use" a join against a changelog instead of a direct
foreign key, more error-prone to get right); git-style content-addressed storage (rejected:
overkill for this scale/scope, adds operational complexity with no requirement driving it).

## 6. Production-safety confirmation flow

**Decision**: Each stored SQL Server connection config carries an `environment` field
(`dev` | `test` | `prod`). The execute endpoint requires an explicit `confirm_production: true`
body field whenever either the source or target connection is tagged `prod`; the endpoint
returns a 409/validation error otherwise. Dry-run has no such gate (it never writes).

**Rationale**: Directly implements Constitution Principle VII and spec FR-016/edge case
"connecting to a database explicitly flagged as production."

**Alternatives considered**: A separate "production mode" toggle on the whole app instance
(rejected: doesn't handle the case of one dev-tagged and one prod-tagged connection in the same
mapping, which the per-connection field handles correctly).

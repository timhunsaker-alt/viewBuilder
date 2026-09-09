# Phase 1 Data Model: Visual SQL Server View/Mapping Builder

Two storage locations, per research.md §2:
- **Metadata store (PostgreSQL, owned by this app)**: `connection_config`, `mapping_definition`,
  `mapping_version`, `enum_translation_table`, `enum_translation_version`, `run_log_entry`.
- **Target SQL Server database (legacy, external)**: `retirement_audit_record` is written into
  a real table there — its shape is user-configured per target (FR-009/FR-010), not fixed by
  this app's own schema, since it must match whatever schema the target system already expects.
  The metadata store keeps a `retirement_audit_binding` describing which target table/columns a
  mapping's retirement writes go to, so runs are reproducible and reviewable.

## connection_config

Represents a named, reusable reference to a SQL Server database (source or target).

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | string | Unique, human-readable (e.g. "Racer1 Legacy Prod") |
| role | enum(`source`, `target`, `either`) | What this connection may be used as in a mapping |
| environment | enum(`dev`, `test`, `prod`) | Drives the production-confirmation gate (FR-016) |
| host, port, database | string/int | Connection target |
| credential_ref | string | Opaque reference into a secrets store — **never** the raw
  credential itself (Constitution Principle VI) |
| created_at, updated_at | timestamp | |

**Validation rules**: `environment = prod` connections cannot be deleted while any
`mapping_version` referencing them has a `run_log_entry` with `outcome = completed` (preserve
auditability). `credential_ref` is write-only through the API — never returned in a GET.

## mapping_definition

The stable, named identity of a mapping across all its versions.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | string | Unique |
| kind | enum(`column_mapping`, `retirement`) | A retirement mapping additionally carries
  retirement configuration (below) |
| source_connection_id | FK → connection_config | Must have role in (`source`,`either`) |
| source_table | string | Schema-qualified table name introspected from the source connection |
| target_connection_id | FK → connection_config | Must have role in (`target`,`either`) |
| target_table | string | Schema-qualified table/view name |
| current_version_id | FK → mapping_version | Points at the latest version |
| created_at | timestamp | |

## mapping_version

An immutable snapshot of a mapping's column links (Constitution Principle II).

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| mapping_definition_id | FK → mapping_definition | |
| version_number | int | Monotonically increasing per definition |
| column_links | JSON | List of `{source_column, target_column, enum_translation_version_id?}` |
| retirement_config | JSON, nullable | Only set when `kind = retirement`: `{status_column,
  retired_value_codes[], reason_column, row_identity_column, audit_binding}` |
| row_identity_column | string | Source column(s) used as the row's identity for
  dedup/traceability (spec Assumptions) |
| created_at | timestamp | Immutable once created — edits always insert a new version |

**Validation rules**: `column_links` entries referencing an `enum_translation_version_id` are
only valid if that enum-translation version's parent table was explicitly attached to that
source column (FR-005). A version, once referenced by any `run_log_entry`, is immutable — no
update endpoint may modify `column_links` or `retirement_config` on an existing version row.

## enum_translation_table

The stable, named identity of a reusable enum lookup, independent of any one mapping (FR-006).

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | string | Unique (e.g. "LegacyRetirementReasonCodes") |
| current_version_id | FK → enum_translation_version | |
| created_at | timestamp | |

## enum_translation_version

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| enum_translation_table_id | FK → enum_translation_table | |
| version_number | int | Monotonically increasing per table |
| entries | JSON | List of `{code, translated_value}`; codes unique within a version |
| created_at | timestamp | Immutable once created |

**Validation rules**: `entries` codes MUST be unique within a version. A version referenced by
any `run_log_entry` is immutable.

## run_log_entry

One dry-run or execution of a specific mapping version (FR-014).

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| mapping_version_id | FK → mapping_version | |
| mode | enum(`dry_run`, `execute`) | |
| operator | string | Single-operator system for v1 (spec Assumptions), still recorded |
| started_at, completed_at | timestamp | |
| outcome | enum(`completed`, `partially_completed`, `failed`) | |
| source_rows_read | int | |
| target_rows_written | int | 0 for dry_run |
| retirement_records_written | int | 0 for dry_run |
| untranslatable_rows_flagged | int | Rows with an unmapped enum code (FR-008) |
| sample_rows | JSON | Small sample of source→translated/mapped values, for dry-run review
  (US4 AC2) — capped at a fixed sample size, not the full result set |
| production_confirmed | boolean | True only if this run touched a `prod`-tagged connection
  and the explicit confirmation flag was set (FR-016) |

**State transitions**: `run_log_entry` rows are append-only once `completed_at` is set —
re-running always creates a new entry, never updates a prior one (Constitution Principle I:
every run must be reconstructable).

## retirement_audit_binding (part of mapping_version.retirement_config)

Describes where, in the *target* SQL Server database, retirement audit rows get written.

| Field | Type | Notes |
|---|---|---|
| audit_table | string | Schema-qualified target table name |
| row_identity_target_column | string | Where the retired row's identity is written |
| reason_target_column | string | Where the translated retirement reason is written |
| timestamp_target_column | string | Where the retirement timestamp is written |
| mapping_version_target_column | string, nullable | Optional column to stamp with this app's
  mapping_version id for cross-referencing back into this app's own run logs |

**Validation rules**: Existence and type-compatibility of every referenced target column MUST
be checked at dry-run/execute time against a live schema introspection (FR-015), not just at
mapping-save time, since the target schema can drift between save and run.

## Entity relationships

```text
connection_config ──< mapping_definition >── connection_config
                              │  (source)         (target)
                              │
                        mapping_version ──< run_log_entry
                              │
                              │ (column_links reference)
                              ▼
                  enum_translation_version >── enum_translation_table
```

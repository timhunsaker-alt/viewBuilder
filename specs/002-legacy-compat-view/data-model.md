# Phase 1 Data Model: Legacy-Shape Compatibility View & Reconciliation

All entities below live in the existing Postgres metadata store (same database as
001-sql-view-builder's `mapping_definition`/`enum_translation_table`/`run_log_entry`
tables), following the same immutable-version-append discipline (Constitution Principle
II). The `connection_config` table from 001 is reused unchanged.

## legacy_shape_capture

A snapshot of the old table's column list/order/types, captured explicitly (not
inferred implicitly at every use) so drift can be detected (FR-013).

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | string | Unique, human-readable (e.g. "LoanApplication legacy shape") |
| connection_id | FK → connection_config | Where the old table lives |
| table_name | string | Schema-qualified old table name |
| columns | JSON | Ordered list of `{name, type, nullable}`, captured at snapshot time |
| captured_at | timestamp | |

**Validation rules**: Re-capturing (creating a new `legacy_shape_capture` row pointed at
the same table) is always allowed and does not invalidate prior captures — a
`view_definition_version` records which capture it was built against, so drift is
detected by comparing a live introspection of `table_name` to the referenced capture at
preview/deploy/reconcile time (FR-013), not by mutating the capture itself.

## view_definition / view_definition_version

Mirrors `mapping_definition`/`mapping_version` from 001: a stable identity plus immutable
versions.

### view_definition

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | string | Unique — also the name the deployed VIEW is created under (FR-006); validated to differ from the referenced legacy_shape_capture's table_name (research.md §5) |
| legacy_shape_capture_id | FK → legacy_shape_capture | |
| target_connection_id | FK → connection_config | Where the view gets deployed and where the new-schema tables live (assumes same connection for the new schema + deploy target; cross-connection new-schema joins are an edge case flagged for FR-002 validation, not assumed away) |
| current_version_id | FK → view_definition_version | |
| created_at | timestamp | |

### view_definition_version

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| view_definition_id | FK → view_definition | |
| version_number | int | Monotonically increasing per definition |
| join_graph | JSON | List of `{left_table, left_column, right_table, right_column, join_type}` (research.md §4) |
| column_mappings | JSON | List of `{legacy_column, source_table, source_column_or_expression, column_status, notes}` — one entry per column in the referenced legacy_shape_capture; validated complete (FR-004) |
| generated_sql | text | The exact `CREATE OR ALTER VIEW ...` statement this version produces — captured verbatim at preview time and re-validated identical at deploy time |
| created_at | timestamp | Immutable once created |

`column_status` is one of `Mapped` (default — a real, live source), `Retired` (no live
source; the generated SQL casts `NULL` for this column instead of reading one), `Transient`
(has a real source today but is expected to go away/change soon), or `Historical` (reflects
fixed/no-longer-updated data). Every column, regardless of status, is wrapped in
`CAST(... AS <its own legacy type>)` in the generated SQL (ddl_generator.py) so the view's
output always matches the old table's declared type — a `Retired` column casts
`NULL AS <type>` instead of reading any (possibly stale) configured source. `notes` is a
free-text field carried through to `legacy_view_column_rule` below.

**Validation rules**: `column_mappings` MUST cover every column in
`legacy_shape_capture.columns`, in the same order (FR-004/FR-006). Every column whose
`column_status` is not `Retired` MUST have a non-empty `source_column_or_expression` — a
column with no live source must be marked `Retired` rather than left unsourced. `join_graph`
MUST leave no table unreachable from the others (FR-002). A version, once referenced by any
`view_deployment_log` entry, is immutable — no update endpoint may modify `join_graph`,
`column_mappings`, or `generated_sql` on an existing version row.

## view_deployment_log

One preview or deploy of a specific view definition version (FR-005/FR-008), analogous to
001's `run_log_entry` but for DDL rather than row-copy.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| view_definition_version_id | FK → view_definition_version | |
| mode | enum(`preview`, `deploy`) | |
| operator | string | |
| started_at, completed_at | timestamp | |
| outcome | enum(`completed`, `failed`) | |
| sample_rows | JSON | Populated for `preview` (and optionally `deploy`) — a capped sample of rows the view produces |
| column_diff | JSON, nullable | For a `deploy` where a prior version was already live: `{added: [...], removed: [...], reordered: [...]}` relative to the previously-deployed version (US2 AC3) |
| production_confirmed | boolean | Mirrors 001's `run_log_entry.production_confirmed` — required true for `mode=deploy` against a `prod`-tagged `target_connection` |

## legacy_view_column_rule

An append-only governance record, written fresh every time a view_definition_version is
saved (create or new version) — one row per legacy column, describing how that column was
treated in that exact version. Rows are never updated after being written (Constitution
Principle II extended to this table): a later save writes a new set of rows rather than
editing the prior set, so the full history of how a column's status changed over time is
preserved, not just its current state.

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| view_definition_version_id | FK → view_definition_version | Which version this rule row belongs to |
| legacy_table_name | string | Copied from the referenced `legacy_shape_capture.table_name` at save time |
| compatibility_view_name | string | Copied from `view_definition.name` at save time |
| column_name | string | The legacy column this rule describes (`column_mappings[i].legacy_column`) |
| column_status | enum(`Mapped`, `Retired`, `Transient`, `Historical`) | Copied from `column_mappings[i].column_status` |
| expected_null_flag | boolean | `true` iff `column_status = Retired` at save time — the view is expected to output NULL (cast to the column's own type) for this column |
| notes | text, nullable | Copied from `column_mappings[i].notes` |
| created_at | timestamp | |

## reconciliation_run

One comparison between a deployed view version and its `legacy_shape_capture`'s old table
(FR-009/FR-010).

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| view_definition_version_id | FK → view_definition_version | Which deployed version was compared |
| identity_column | string | The user-designated key column used to match rows across both sides |
| started_at, completed_at | timestamp | |
| outcome | enum(`completed`, `partially_completed`, `failed`) | `partially_completed` if interrupted mid-run (edge case in spec.md) — never reported as a clean match |
| rows_matched | int | Rows present on both sides with all compared columns equal |
| rows_old_only | int | |
| rows_view_only | int | |
| rows_with_column_mismatch | int | |
| row_inflation_flagged | boolean | Set when a join produced more than one view row per old-table identity (FR-014) — distinct from an ordinary mismatch |
| discrepancy_detail | JSON | Capped sample of per-row/column detail: `{identity, column, old_value, view_value}` entries, enough to investigate specific discrepancies (US3 AC2) without re-querying the databases |

## xml_field_mapping / xml_field_mapping_version

Per-old-table-column configuration of where that value lives in the legacy XML document
store (FR-011), versioned the same way as everything else (Principle II).

### xml_field_mapping

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| legacy_shape_capture_id | FK → legacy_shape_capture | Which old-table shape this mapping's columns belong to |
| xml_connection_id | FK → connection_config | Where the XML document table lives (may equal or differ from the old table's connection) |
| xml_table_name | string | Schema-qualified table holding the XML documents |
| xml_identity_column | string | The column on `xml_table_name` matching the shared identity key |
| xml_payload_column | string | The `xml` (or castable text) column holding the document |
| current_version_id | FK → xml_field_mapping_version | |

### xml_field_mapping_version

| Field | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| xml_field_mapping_id | FK → xml_field_mapping | |
| version_number | int | |
| field_paths | JSON | List of `{legacy_column, xpath, cast_type}` — not required to cover every legacy column, only the ones under investigation (US4 AC4: added incrementally) |
| created_at | timestamp | Immutable once created |

## xml_lookup_result

Not persisted as its own versioned entity (a lookup is a query, not a definition) — the
result of one `POST .../xml-lookup` call for a specific `(reconciliation_run_id or ad hoc
identity, legacy_column)` pair, returned directly by the API and optionally attached back
onto the relevant `reconciliation_run.discrepancy_detail` entry for later reference.

| Field | Type | Notes |
|---|---|---|
| identity | string | |
| legacy_column | string | |
| outcome | enum(`found`, `field_missing`, `document_not_found`) | The three distinct outcomes required by FR-012 |
| value | string, nullable | Populated only when `outcome = found` |

## Entity relationships

```text
connection_config ──< legacy_shape_capture
                            │
                    view_definition ──< view_definition_version ──< view_deployment_log
                                              │        │                   │
                                              │        └──< legacy_view_column_rule
                                              │             (one row per legacy column,
                                              │              written fresh every save)
                                              └──────< reconciliation_run ─┘
                                              (compares this version's live view
                                               output against legacy_shape_capture's
                                               old table)

legacy_shape_capture ──< xml_field_mapping ──< xml_field_mapping_version
                                 │
                        (xml_lookup_result is computed on demand, not stored as its
                         own table — see above)
```

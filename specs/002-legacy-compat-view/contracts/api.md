# API Contract: Legacy-Shape Compatibility View & Reconciliation (v1)

Base path: `/api/v1` (same versioned prefix as 001-sql-view-builder; these are additional
routes in the same API surface, not a separate service).

## Legacy shape capture

### `POST /legacy-shapes`
Capture the old table's current shape. Body: `{name, connection_id, table_name}`.
Introspects `table_name` on `connection_id` immediately and stores the column list/order/
types (FR-001). Errors with `connection_unreachable` if the connection can't be reached —
never silently returns a stale/cached shape (same discipline as 001's schema endpoint).

### `GET /legacy-shapes` / `GET /legacy-shapes/{id}`
List/fetch captures.

### `GET /legacy-shapes/{id}/drift`
Re-introspects the live table and reports whether it still matches the captured shape
(FR-013) — `{drifted: boolean, added_columns: [...], removed_columns: [...],
retyped_columns: [...]}`. Called automatically before every preview/deploy/reconcile, and
exposed directly here so a user can check drift without triggering one of those.

## View definitions

### `POST /view-definitions`
Create a new `view_definition` + its first `view_definition_version`. Body: `{name,
legacy_shape_capture_id, target_connection_id, join_graph, column_mappings}`, where each
`column_mappings` entry is `{legacy_column, source_table?, source_column_or_expression?,
column_status?, notes?}`. `column_status` is one of `Mapped` (default), `Retired`,
`Transient`, `Historical` — a `Retired` column needs no `source_table`/
`source_column_or_expression` at all (the view casts `NULL` for it instead); every other
status still requires one. Rejects with `mapping_invalid` if `column_mappings` doesn't
cover every legacy-shape column (FR-004), a non-`Retired` column has no source expression,
an entry's `column_status` isn't one of the four values, or `join_graph` leaves a table
unreachable (FR-002). Rejects with `name_collision` if `name` equals the legacy shape's own
`table_name` (research.md §5).

Every generated column — regardless of status — is wrapped in
`CAST(... AS <that column's own legacy type>)` in the resulting view SQL, so the view's
output always matches the old table's declared types, not just its column names/order.

Saving (here or via `.../versions` below) also writes one `legacy_view_column_rule` row
per legacy column — see `GET .../column-rules`.

### `GET /view-definitions` / `GET /view-definitions/{id}`
List/fetch, `current_version_id` included.

### `GET /view-definitions/{id}/versions`
Full version history, each with its `generated_sql` (FR-008).

### `POST /view-definitions/{id}/versions`
Save an edit as a new version (never mutates an existing version — Principle II). Same
body shape as create, minus `name`/`legacy_shape_capture_id`/`target_connection_id`
(immutable properties of the definition, same pattern as 001's mapping-version contract).

### `GET /view-definitions/{id}/column-rules`
The append-only `legacy_view_column_rule` history for this definition: every version's
save (create or `.../versions`) writes a fresh row per legacy column — `{legacy_table_name,
compatibility_view_name, column_name, column_status, expected_null_flag, notes}` — so this
list can show how a column's status changed across versions, not just its current state.
Rows are never updated once written.

### `POST /view-definitions/{id}/preview`
Body: `{view_definition_version_id?}` (defaults to current version). Re-checks drift
(`GET .../drift`) first and blocks with `schema_mismatch` if drifted. Generates the
`CREATE OR ALTER VIEW` SQL, runs it as a preview `SELECT` (not deployed) against
`target_connection_id`, and returns a `view_deployment_log`-shaped payload (`mode:
"preview"`) with `sample_rows` and the generated SQL. Zero DDL is executed.

### `POST /view-definitions/{id}/deploy`
Body: `{view_definition_version_id?, confirm_production?: boolean}`. Returns `409`
(`production_confirmation_required`) with no DDL executed if `target_connection_id` is
`environment: prod` and `confirm_production` was not `true` (FR-016-equivalent, same
pattern as 001). On success, executes `CREATE OR ALTER VIEW` for real, computes
`column_diff` against whatever version was previously live (US2 AC3), and returns the
completed `view_deployment_log`.

### `GET /view-definitions/{id}/deployments`
List `view_deployment_log` entries (both `preview` and `deploy` modes), filterable by
`mode`.

## Reconciliation

### `POST /view-definitions/{id}/reconcile`
Body: `{view_definition_version_id?, identity_column}`. Requires the referenced version to
have at least one successful `deploy` log entry (returns `not_deployed` otherwise — you
can't reconcile a view that was only ever previewed). Runs the keyed comparison
(research.md §2) and returns a `reconciliation_run`.

For any legacy column whose `legacy_view_column_rule.column_status` is `Retired` on
this version, the comparison ignores that column entirely when the view's value for
it is `NULL` (the expected output for a retired column, per ddl_generator.py's
`CAST(NULL AS <old type>)`) — whatever the old table still holds there is not
compared and never appears in `discrepancy_detail`. If a retired column somehow
comes back non-`NULL` (e.g. a stale deploy that wasn't actually retired), it is
compared normally and flagged like any other mismatch.

### `GET /view-definitions/{id}/reconciliations` / `GET /reconciliations/{id}`
List/fetch reconciliation runs, the latter including `discrepancy_detail`.

## XML field mappings & lookup

### `POST /xml-field-mappings`
Create a new `xml_field_mapping` + first version. Body: `{legacy_shape_capture_id,
xml_connection_id, xml_table_name, xml_identity_column, xml_payload_column, field_paths}`.

### `GET /xml-field-mappings` / `GET /xml-field-mappings/{id}`
List/fetch, with `current_version_id`.

### `POST /xml-field-mappings/{id}/versions`
Save an edit (e.g. adding a `field_paths` entry for a newly-investigated column, US4 AC4)
as a new version.

### `POST /xml-field-mappings/{id}/lookup`
Body: `{identity, legacy_column}`. Runs the pushdown `.value()`/`EXISTS` query
(research.md §1) against the configured XML table and returns an `xml_lookup_result`:
`{identity, legacy_column, outcome, value?}` where `outcome` is exactly one of `found`,
`field_missing`, `document_not_found` (FR-012). Returns `mapping_invalid` if no
`field_paths` entry exists yet for `legacy_column` on this mapping's current version.

## Error shape (all endpoints)

Same shape as 001: `{ "error": { "code": "string", "message": "human-readable", "details":
{} } }`. New `code` values introduced by this feature: `name_collision`,
`schema_mismatch` (reused from 001's meaning — a referenced table/column no longer
matches), `not_deployed`, alongside 001's existing `not_found`,
`production_confirmation_required`, `connection_unreachable`, `mapping_invalid`,
`write_constraint_violation`.

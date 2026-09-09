# API Contract: viewBuilder Backend (v1)

Base path: `/api/v1`. All endpoints are JSON over HTTP. No auth in v1 (spec Assumptions) —
routes are structured under a versioned prefix so an auth layer can be added later without
reshaping URLs (Constitution Technology Constraints).

## Connections

### `GET /connections`
List saved `connection_config` entries. **Never** includes `credential_ref` or any secret
material in the response.

### `POST /connections`
Create a connection config. Body: `{name, role, environment, host, port, database,
credential_ref}`. `credential_ref` is stored but never echoed back.

### `GET /connections/{id}/schema`
Introspect the live database at this connection: list tables, and for a given
`?table=schema.name` query param, list that table's columns with name/type/nullability
(FR-001/FR-002). Errors clearly if the connection is unreachable — never silently returns a
stale/cached schema.

## Mapping definitions

### `POST /mappings`
Create a new `mapping_definition` + its first `mapping_version`. Body: `{name, kind,
source_connection_id, source_table, target_connection_id, target_table, column_links,
row_identity_column, retirement_config?}`.

### `GET /mappings` / `GET /mappings/{id}`
List/fetch mapping definitions, `current_version_id` included.

### `GET /mappings/{id}/versions`
Full version history for a mapping definition (FR-017).

### `POST /mappings/{id}/versions`
Save an edit as a **new** version (never mutates an existing version — Principle II). Body:
same shape as create. Returns the new `mapping_version`.

## Enum translation tables

### `POST /enum-translations`
Create a new `enum_translation_table` + first version. Body: `{name, entries: [{code,
translated_value}]}`.

### `GET /enum-translations` / `GET /enum-translations/{id}`
List/fetch, with `current_version_id`.

### `POST /enum-translations/{id}/versions`
Save an edit as a new version. Body: `{entries: [{code, translated_value}]}`. Codes unique
within the version, enforced server-side.

## Dry-run & execution

### `POST /mappings/{id}/dry-run`
Body: `{mapping_version_id?}` (defaults to current version). Runs the full read → translate →
would-write pipeline with **zero writes** to target or retirement-audit tables (FR-012).
Returns a `run_log_entry`-shaped payload (`mode: "dry_run"`) including `sample_rows` and
counts, immediately (synchronous for v1 scale — see plan.md Performance Goals).

Response includes, per FR-008, an explicit `untranslatable_rows_flagged` count and a sample of
which source rows/codes had no translation entry — never a guessed value.

### `POST /mappings/{id}/execute`
Body: `{mapping_version_id?, confirm_production?: boolean}`. Returns `409` immediately, with no
writes attempted, if either the source or target connection is `environment: prod` and
`confirm_production` was not `true` (FR-016). On success, performs the real reads/translations/
writes and returns the completed `run_log_entry`.

Untranslatable rows during execute are **not** written with a guessed/defaulted value; they are
counted in `untranslatable_rows_flagged` and the affected rows are skipped, matching what the
preceding dry-run predicted (FR-008, US5 AC3).

Duplicate-retirement protection (FR-011): for `kind: retirement` mappings, execute checks the
target's existing retirement-audit table for rows already carrying this row's identity before
writing a new audit record, and skips/flags rather than duplicating.

Pre-flight schema check (FR-015): before any write, execute re-introspects the source and
target schemas referenced by the mapping version; if a referenced table/column is missing or
now type-incompatible, the whole run fails with a clear error and **no partial writes** occur
for that run.

### `GET /runs` / `GET /runs/{id}`
List/fetch `run_log_entry` records, filterable by `mapping_definition_id` and `mode` (FR-014).

## Error shape (all endpoints)

```json
{ "error": { "code": "string", "message": "human-readable", "details": {} } }
```

`code` values used across this contract include: `connection_unreachable`,
`schema_mismatch`, `untranslated_enum_code`, `production_confirmation_required`,
`duplicate_retirement`, `version_immutable`.

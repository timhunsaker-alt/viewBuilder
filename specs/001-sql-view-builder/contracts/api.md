# API Contract: viewBuilder Backend (v1)

Base path: `/api/v1`. All endpoints are JSON over HTTP. No auth in v1 (spec Assumptions) —
routes are structured under a versioned prefix so an auth layer can be added later without
reshaping URLs (Constitution Technology Constraints).

## Connections

### `GET /connections`
List saved `connection_config` entries. **Never** includes `credential_ref` or any secret
material in the response.

### `POST /connections`
Create a connection config. Body: `{name, role, environment, host, port, database, auth_mode?,
username?, credential_ref?, operator?}`. `auth_mode` is `sql` (default) or
`windows_integrated`. For `sql`, `username` (the real SQL login name) and `credential_ref`
(an opaque pointer, resolved to the actual secret server-side) are both required —
`credential_ref` is stored but never echoed back, and never returned by any `GET`. For
`windows_integrated` (the backend's own Windows/AD service-account identity —
`Trusted_Connection=yes`; see 002-legacy-compat-view/research.md §6 for why this is a single
fixed identity rather than per-end-user delegation), `username`/`credential_ref` must be
omitted entirely — there's no secret to store. Rejects with `invalid_auth_mode` if `auth_mode`
isn't one of the two values, or `mapping_invalid` if the username/credential_ref presence
doesn't match the chosen `auth_mode`.

### `GET /connections/{id}/schema`
Introspect the live database at this connection: list tables, and for a given
`?table=schema.name` query param, list that table's columns with name/type/nullability
(FR-001/FR-002). Errors clearly if the connection is unreachable — never silently returns a
stale/cached schema.

## Mapping definitions

### `POST /mappings`
Create a new `mapping_definition` + its first `mapping_version`. Body: `{name, kind,
source_connection_id, source_table, target_connection_id, target_table, column_links,
row_identity_column, retirement_config?, operator?}`. `operator` defaults to
`"system-operator"` (spec Assumptions: single trusted operator, no auth yet) and is recorded
in the structured audit log (see Audit logging, below) — it is not persisted on the mapping
itself.

### `GET /mappings` / `GET /mappings/{id}`
List/fetch mapping definitions, `current_version_id` included.

### `GET /mappings/{id}/versions`
Full version history for a mapping definition (FR-017).

### `POST /mappings/{id}/versions`
Save an edit as a **new** version (never mutates an existing version — Principle II). Body:
`{column_links, row_identity_column?, retirement_config?, operator?}` — **not** the full
create shape: `name`, `kind`, `source_connection_id`, `source_table`, `target_connection_id`,
and `target_table` are immutable properties of the `mapping_definition` and cannot be changed
by a version save; a version only carries the fields that are actually versioned
(`column_links`, `row_identity_column`, `retirement_config`, per data-model.md
§mapping_version). Omitted `row_identity_column`/`retirement_config` fall back to the
previous version's value. Returns the new `mapping_version`.

## Enum translation tables

### `POST /enum-translations`
Create a new `enum_translation_table` + first version. Body: `{name, entries: [{code,
translated_value}], operator?}`. `operator` defaults to `"system-operator"` and is recorded
in the structured audit log (see Audit logging, below).

### `GET /enum-translations` / `GET /enum-translations/{id}`
List/fetch, with `current_version_id`.

### `POST /enum-translations/{id}/versions`
Save an edit as a new version. Body: `{entries: [{code, translated_value}], operator?}`.
Codes unique within the version, enforced server-side.

## Dry-run & execution

### `POST /mappings/{id}/dry-run`
Body: `{mapping_version_id?, operator?}` (`mapping_version_id` defaults to current version;
`operator` defaults to `"system-operator"` and is recorded on the returned `run_log_entry` as
well as in the structured audit log). Runs the full read → translate → would-write pipeline
with **zero writes** to target or retirement-audit tables (FR-012). Returns a
`run_log_entry`-shaped payload (`mode: "dry_run"`) including `sample_rows` and counts,
immediately (synchronous for v1 scale — see plan.md Performance Goals).

Response includes, per FR-008, an explicit `untranslatable_rows_flagged` count and a sample of
which source rows/codes had no translation entry — never a guessed value.

### `POST /mappings/{id}/execute`
Body: `{mapping_version_id?, operator?, confirm_production?: boolean}`. Returns `409`
immediately, with no writes attempted, if either the source or target connection is
`environment: prod` and `confirm_production` was not `true` (FR-016). On success, performs the
real reads/translations/writes and returns the completed `run_log_entry`.

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

## Audit logging

Every mutating endpoint — `POST /mappings`, `POST /mappings/{id}/versions`,
`POST /enum-translations`, `POST /enum-translations/{id}/versions`,
`POST /mappings/{id}/dry-run`, `POST /mappings/{id}/execute` — emits a structured audit log
line (logger `viewbuilder.audit`, see `backend/src/api/middleware.py::log_audit_event`) on
success, carrying the `operator` from the request body, the `action`, and the affected
resource/version id. This is in addition to (not a replacement for) the durable
`run_log_entry` row written for every dry-run/execute (FR-014) — the audit log line covers the
*definitional* mutations (creating/versioning a mapping or translation table) that
`run_log_entry` alone doesn't record.

## Error shape (all endpoints)

```json
{ "error": { "code": "string", "message": "human-readable", "details": {} } }
```

`code` values actually produced by the implementation: `not_found` (unknown connection,
mapping, mapping version, enum translation table, or run id), `invalid_role` /
`invalid_environment` / `invalid_auth_mode` (`POST /connections` with a `role`/`environment`/
`auth_mode` outside the allowed enum), `mapping_invalid` (`POST /connections` with a
username/credential_ref that doesn't match the chosen `auth_mode`; or `POST /mappings` or
`POST /mappings/{id}/versions` — bad column
link, dangling connection/enum-translation-version reference, or missing retirement config,
FR-026), `enum_translation_invalid` (`POST /enum-translations` or its `/versions` route —
duplicate code within a version, or a malformed entry), `connection_unreachable`
(`GET /connections/{id}/schema`, dry-run, or execute — the source or target SQL Server could
not be reached), `schema_mismatch` (`POST /mappings/{id}/execute` only — pre-flight
schema-drift check, FR-015), `production_confirmation_required` (`POST
/mappings/{id}/execute` only — FR-016, HTTP 409), `write_constraint_violation`
(`POST /mappings/{id}/execute` only — the target database itself rejected a specific row
via a NOT NULL/PK/FK/CHECK constraint, e.g. a mapping omits a NOT NULL target column; HTTP
422. Distinct from `connection_unreachable`: the connection and query both worked, the row
was invalid for that table's schema).

Untranslatable rows (Principle III / FR-008) and duplicate-retirement rows (FR-011) are
**not** modeled as request-level errors — a single row failing either check does not fail the
whole dry-run/execute call. Instead they are counted and, for dry-run, sampled inside the
successful `run_log_entry` response (`untranslatable_rows_flagged`, and
`retirement_records_written` excludes duplicate-skipped rows) — this reflects FR-008/FR-012's
"flag, don't fail the run" requirement more precisely than a per-row error code would.
Similarly, no endpoint currently allows updating an existing `mapping_version` or
`enum_translation_version` (Principle II makes them immutable by construction — there is no
route to attempt the mutation), so a `version_immutable` error code has no code path that
would ever raise it and is not implemented.

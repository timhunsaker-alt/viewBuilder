# Quickstart: Legacy-Shape Compatibility View & Reconciliation

Builds on the 001-sql-view-builder quickstart — start there first (local infra, backend,
frontend all running against `docker compose up -d` in `backend/docker/`).

## Additional local fixtures this feature needs

The docker-compose MS SQL Server fixture gains, alongside 001's sample tables:

- An **old wide table** (e.g. `dbo.legacy_loan_application`) with ~15-20 sample columns
  standing in for the real 80-column case, enough to exercise ordering/typing.
- A **5-table normalized replacement schema** (e.g. `dbo.loan_application`,
  `dbo.loan_applicant`, `dbo.loan_collateral`, `dbo.loan_underwriting`,
  `dbo.loan_document_ref`) holding the same data split up, joined by a shared
  `application_id`.
- An **XML document table** (e.g. `dbo.legacy_application_xml`) with an `application_id`
  key column and an `xml` payload column, containing a handful of sample documents —
  including at least one deliberately missing a field the normalized schema is also
  missing, so US4's "not found in XML either" outcome is exercisable.

## Golden path

1. Open the frontend's `/legacy-shapes/new` page, pick the connection, select
   `dbo.legacy_loan_application` from the table dropdown, and click **Capture shape** —
   captures its column list/order.
2. Open the frontend's view-definition editor; the join-graph canvas shows the 5
   normalized tables. Draw join edges between them (e.g.
   `loan_application.application_id = loan_applicant.application_id`, etc.) until every
   table is connected.
3. Below the join graph, the column-mapping table lists every legacy-shape column; map
   each one to a source table + column from the joined tables.
4. Click **Preview** — confirm the generated `CREATE VIEW` SQL looks right and the sample
   rows show data in the expected column order.
5. Click **Deploy** — confirm the view now exists in the target database and its
   introspected column list/order matches the legacy shape exactly.
6. Run **Reconcile** against the old table with `application_id` as the identity column —
   confirm a clean deploy reports zero discrepancies, and a deliberately-wrong column
   mapping (redeploy a version with one column pointed at the wrong source) is correctly
   flagged.
7. For a flagged column, open the XML lookup panel. There is currently no frontend form
   for creating the top-level `xml_field_mapping` itself (which XML table/identity/
   payload columns to use) — create it once via `POST /xml-field-mappings` pointed at
   `dbo.legacy_application_xml` before opening the panel. Select that mapping, configure
   a `field_paths` entry (XPath into the sample XML
   documents) for the flagged column, and run the lookup — confirm it distinguishes
   `found` (value returned), `field_missing` (document exists, field absent), and
   `document_not_found`. `application_id` 5's sample document deliberately omits
   `<CollateralValue>` (mirroring that row's `NULL` collateral value in the normalized
   schema) — look up `collateral_value_cents` for identity `5` to see `field_missing`;
   `application_id` 10 has no XML document at all, so any lookup against it reports
   `document_not_found`.

## Tests

```bash
cd backend && pytest                 # unit + integration (spins up against docker-compose mssql)
cd frontend && bun run test          # unit, including JoinGraphCanvas
cd frontend && bun run test:e2e      # Playwright: build -> preview -> deploy -> reconcile -> xml-lookup
```

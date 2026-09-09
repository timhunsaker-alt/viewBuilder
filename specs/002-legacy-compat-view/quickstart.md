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

1. `POST /legacy-shapes` pointed at `dbo.legacy_loan_application` — captures its column
   list/order.
2. Open the frontend's view-definition editor; the join-graph canvas shows the 5
   normalized tables. Draw join edges between them (e.g.
   `loan_application.application_id = loan_applicant.application_id`, etc.) until every
   table is connected.
3. Switch to column-mapping mode; map every legacy-shape column to a source column from
   the joined tables.
4. Click **Preview** — confirm the generated `CREATE VIEW` SQL looks right and the sample
   rows show data in the expected column order.
5. Click **Deploy** — confirm the view now exists in the target database and its
   introspected column list/order matches the legacy shape exactly.
6. Run **Reconcile** against the old table with `application_id` as the identity column —
   confirm a clean deploy reports zero discrepancies, and a deliberately-wrong column
   mapping (redeploy a version with one column pointed at the wrong source) is correctly
   flagged.
7. For a flagged column, open the XML lookup panel, configure a `field_paths` entry
   (XPath into the sample XML documents), and run the lookup — confirm it distinguishes
   `found` (value returned), `field_missing` (document exists, field absent), and
   `document_not_found`.

## Tests

```bash
cd backend && pytest                 # unit + integration (spins up against docker-compose mssql)
cd frontend && bun run test          # unit, including JoinGraphCanvas
cd frontend && bun run test:e2e      # Playwright: build -> preview -> deploy -> reconcile -> xml-lookup
```

# Feature Specification: Legacy-Shape Compatibility View & Reconciliation

**Feature Branch**: `002-legacy-compat-view`

**Created**: 2026-09-09

**Status**: Draft

**Input**: User description: "We recently migrated to a new data model with more tables. Before, things were stored in XML and in large tables (e.g., an application table for provisioning loan accounts, with customer info, collateral info — 80 columns in one table). In the new data model that's split across 5 tables. We need a view that old reports can reference just like they would the old table, with everything back in the same column order the old table had. Then we need to reconcile the new view against the old table, and if there is missing data, look back at the XML to find it."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build a compatibility view that reconstructs the old table's exact shape (Priority: P1)

An engineer picks the old wide table (still live) to capture its exact column list and order, then picks the new normalized tables that together hold the same data. On the visual canvas, they map each old column to its source in the new schema (a column from one of the new tables) and configure how the new tables join together (e.g., a shared application/account identifier). The tool previews the resulting `SELECT` shape and a sample of rows, then generates and deploys a SQL VIEW whose output has the same columns, in the same order, as the old table — so an existing report that queries the old table's column list gets identical shape back from the view.

**Why this priority**: This is the entire point of the feature — without a working compatibility view, nothing downstream (reconciliation, XML fallback) has anything to operate on.

**Independent Test**: Can be fully tested by pointing the tool at a legacy wide table and its normalized replacement tables, building the view definition, previewing it, deploying it, and running the exact column list of the old table against the deployed view to confirm identical column names/order/types.

**Acceptance Scenarios**:

1. **Given** an old wide table is selected, **When** the tool introspects it, **Then** its full column list is captured in its original left-to-right order and displayed as the required output shape.
2. **Given** the new normalized tables are selected, **When** the user configures how they join together (e.g., shared identifier columns), **Then** the tool validates that every new table is reachable via the configured joins from a single starting table.
3. **Given** every old column has been mapped to a new-schema source expression, **When** the user previews the view, **Then** the tool shows the generated `SELECT` statement and a sample of rows produced by actually running it against live data, without deploying anything.
4. **Given** a preview has been reviewed, **When** the user deploys the view, **Then** the tool creates (or updates) a real SQL VIEW in the target database whose column list, order, and (as far as SQL types allow) data types match the old table's.
5. **Given** an old column has no mapped source configured, **When** the user attempts to preview or deploy, **Then** the tool blocks with a clear list of which old columns remain unmapped, rather than silently omitting or reordering columns.

---

### User Story 2 - Version and safely redeploy the view definition (Priority: P1)

The engineer edits the view definition later (a join changes, a column's source expression is corrected) and redeploys. Each deploy is a new, immutable version; the tool never silently overwrites a previously-deployed definition's history, and every deploy is logged with what changed.

**Why this priority**: A compatibility view feeds live reports; an unreviewed or unversioned redeploy could silently reorder or drop a column reports depend on. This is exactly the class of risk the rest of this system (and the project constitution) treats as non-negotiable.

**Independent Test**: Can be fully tested by deploying a view definition, editing a mapping, redeploying, and confirming both that the live view now reflects the new definition and that the previous version's full definition is still retrievable from history.

**Acceptance Scenarios**:

1. **Given** a view definition has been deployed at least once, **When** the user edits any mapping or join and redeploys, **Then** a new version is recorded without altering the record of the previously-deployed version.
2. **Given** multiple versions exist, **When** the user views the definition's history, **Then** they can see, for each version, the exact generated SQL and when/by whom it was deployed.
3. **Given** a redeploy would change the view's column list or order, **When** the user reviews the pre-deploy preview, **Then** the tool explicitly highlights which columns were added, removed, or reordered relative to the currently-live version.

---

### User Story 3 - Reconcile the view against the still-live old table (Priority: P1)

Once the view is deployed, the engineer runs a reconciliation: the tool compares the view's output to the old table's actual current data, row by row (matched by a shared identity/key column) and column by column, and produces a clear report of what doesn't match — rows present in one side but not the other, and per-column value differences for rows present in both.

**Why this priority**: The compatibility view is only trustworthy if it's been shown to actually reproduce the old table's data; this is the verification step that makes the rest of the feature meaningful, and it's independently valuable even before any XML fallback exists.

**Independent Test**: Can be fully tested by deploying a view with a deliberately introduced discrepancy (e.g., one mapped column pointing at the wrong new-schema source) and confirming the reconciliation report correctly flags exactly that discrepancy and nothing else.

**Acceptance Scenarios**:

1. **Given** a deployed view and its source old table, **When** the user runs a reconciliation, **Then** the tool reports, for the identity/key column's current population: how many rows match exactly, how many rows exist in the old table but not the view (or vice versa), and how many rows exist in both but with at least one differing column.
2. **Given** a row exists in both but with differing columns, **When** the user inspects that row in the report, **Then** they see, per differing column, the old table's value and the view's value side by side.
3. **Given** a reconciliation has run, **When** the user views reconciliation history, **Then** each run is logged with its scope (view version, row/column counts, timestamp) the same way a migration run is logged elsewhere in this system.
4. **Given** the old table changes between reconciliation runs (it remains live during the transition), **When** the user re-runs reconciliation, **Then** the new run reflects current data and does not need to be reconciled against a stale snapshot.

---

### User Story 4 - Fall back to legacy XML when the new schema is missing data (Priority: P2)

For a specific old-table column flagged as missing or mismatched by reconciliation, the engineer looks up whether the correct value actually exists in the legacy XML documents (stored in a separate document table, keyed by the same identity used elsewhere) — using a configured mapping from old-table column to a location within the XML — so they can tell whether the gap is a genuine data-migration bug or expected (the value never existed).

**Why this priority**: This directly serves the "where did the data go" investigation, but it depends on User Story 3 already having identified which rows/columns are actually in question — there's nothing to look up until reconciliation has flagged something.

**Independent Test**: Can be fully tested by taking a row/column flagged by reconciliation as missing, configuring the XML field lookup for that column, running the lookup, and confirming it returns the value found in the XML document (or clearly reports "not found in XML either" when it truly isn't there).

**Acceptance Scenarios**:

1. **Given** an old-table column has been configured with a location within the legacy XML documents, **When** the user runs an XML lookup for a specific flagged row, **Then** the tool retrieves that row's XML document (via the shared identity key) and extracts the configured field.
2. **Given** the configured field is present in the XML document, **When** the lookup completes, **Then** the tool reports the value found, letting the user compare it against the old table's value and the view's value.
3. **Given** the configured field is absent from the XML document as well, **When** the lookup completes, **Then** the tool clearly reports "not found in XML" rather than a blank/ambiguous result, so the user knows the data is genuinely gone rather than un-looked-up.
4. **Given** no XML field mapping has been configured yet for a flagged column, **When** the user wants to investigate it, **Then** the tool lets them add that mapping (old column → location within the XML) without needing to touch the view definition itself.

---

### Edge Cases

- What happens when the new schema's join configuration produces more than one row per old-table identity (e.g., a one-to-many join used where one-to-one was expected)? The tool must surface this as a distinct problem (row-count inflation) rather than reporting it as a generic mismatch.
- What happens when the old table and the new tables live on different database connections? The view-deployment and reconciliation steps must clearly support (or clearly reject, with an explicit message) cross-connection scenarios rather than silently assuming same-connection.
- What happens when the old table itself changes shape (a column added/removed/retyped) after the compatibility view was built? The tool must detect this at preview/deploy/reconcile time and flag it, not silently produce a view whose shape no longer matches.
- What happens when a reconciliation run is interrupted partway through a large old table? Partial results must be clearly marked incomplete, never presented as a clean "fully matches" result.
- What happens when the legacy XML document for a given identity doesn't exist at all (not just missing the specific field)? This must be distinguishable from "document exists but field is missing."
- What happens when the view's deployed SQL name collides with the old table's real name (they can't coexist under an identical name in the same database)? The tool deploys the view under its own distinct name during the transition; actually renaming/retiring the old table and repointing reports to the view's final name is a deliberate, separate, human-reviewed cutover step outside this tool's automated scope (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST introspect a selected old (source-of-truth-shape) table and capture its full column list, in original order, with data types.
- **FR-002**: System MUST let the user select multiple new-schema tables and configure the join relationships between them (which columns relate which tables), validating that all selected tables are reachable from one another via the configured joins.
- **FR-003**: System MUST let the user map each old-table column to a source expression (a column, or a join-derived value) from the configured new-schema tables, on the same visual canvas used for column mapping elsewhere in this system.
- **FR-004**: System MUST block preview and deployment while any old-table column remains unmapped, and MUST clearly list which columns are unmapped.
- **FR-005**: System MUST let the user preview the exact generated view SQL and a live sample of rows it would produce, without deploying anything, before every deploy.
- **FR-006**: System MUST deploy the previewed definition as a real SQL VIEW whose output column list and order exactly match the captured old-table shape.
- **FR-007**: System MUST treat each deployed view definition as a versioned, immutable record (consistent with the versioning approach used for mapping definitions elsewhere in this system) — editing and redeploying creates a new version, never overwrites a prior one's record.
- **FR-008**: System MUST log every deploy (and every preview, at minimum for audit purposes) with the view version, the generated SQL, and who/when performed it.
- **FR-009**: System MUST let the user run a reconciliation between a deployed view and its captured old table, matched by a user-designated identity/key column, reporting row-level presence differences (old-only, view-only) and column-level value differences for rows present on both sides.
- **FR-010**: System MUST log every reconciliation run (view version compared, row/column counts, timestamp, outcome) the same way migration runs are logged elsewhere in this system.
- **FR-011**: System MUST let the user configure, per old-table column, a location within the separate legacy XML document store (keyed by the shared identity) where that column's value can alternatively be found.
- **FR-012**: System MUST let the user run an XML fallback lookup for a specific flagged row/column, retrieving the corresponding XML document by identity and extracting the configured field, and MUST distinguish "document not found," "field not found in document," and "value found" as three distinct outcomes.
- **FR-013**: System MUST detect, at preview/deploy/reconcile time, whether the old table's own shape has drifted (column added/removed/retyped) since it was last captured, and block with a clear message rather than silently proceeding.
- **FR-014**: System MUST flag, distinctly from an ordinary value mismatch, the case where a configured join produces more than one new-schema row per old-table identity.

### Key Entities

- **Legacy Shape Capture**: A snapshot of the old table's column list, order, and types at the time it was captured, used as the required output contract for the compatibility view and to detect later drift.
- **Compatibility View Definition**: A named, versioned mapping from each legacy-shape column to a source expression over one or more new-schema tables, plus the join configuration connecting those tables; each version records the exact deployed SQL.
- **Deployment Run Log**: A record of one preview or deploy of a compatibility view definition version — what SQL was generated/deployed, when, by whom.
- **Reconciliation Run**: A record of one comparison between a deployed view version and its legacy-shape old table — counts of matching rows, old-only rows, view-only rows, and per-column mismatches, plus a per-row/column detail sufficient to investigate a specific discrepancy.
- **XML Field Mapping**: A per-old-table-column configuration pointing at where that value lives within the legacy XML document store, used by the fallback lookup.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An engineer can go from selecting an old table and its replacement tables to a deployed, live compatibility view in under 30 minutes for an 80-column table split across 5 new tables, without hand-writing SQL.
- **SC-002**: 100% of old-table columns are present, correctly ordered, and correctly typed (as far as the target SQL dialect allows) in every deployed view version — verified by comparing the view's introspected shape against the captured legacy shape after every deploy.
- **SC-003**: A reconciliation run against a fully-consistent old table and view reports zero discrepancies; a reconciliation run against a deliberately-broken mapping correctly identifies 100% of the deliberately-introduced discrepancies and no false positives on unaffected columns.
- **SC-004**: For any column flagged by reconciliation with a configured XML field mapping, the fallback lookup correctly distinguishes "found in XML," "document exists but field missing," and "document not found" in 100% of cases tested against known sample documents.
- **SC-005**: Every deployed view version and every reconciliation run can be reconstructed after the fact (what was deployed, what was compared, what was found) purely from the tool's own logs, without needing to inspect the database directly.

## Assumptions

- The old table and the new normalized tables are reachable from connections already modeled by this system (SQL Server, via `connection_config`); this feature does not introduce a new database engine.
- A shared identity/key value exists (or can be derived via the configured joins) that uniquely identifies one "old-table row's worth" of data across the new schema — reconciliation and XML lookup both key off of this.
- The legacy XML document store is itself a queryable table (columns include at least an identity key and an XML/text payload column), reachable the same way any other SQL Server table/view is in this system — not a filesystem or object-storage document store.
- The compatibility view is deployed under its own distinct name during the transition (it cannot share the old table's exact name while the old table still exists in the same database). Actually retiring the old table and repointing reports to reuse its original name is a deliberate, human-reviewed cutover performed outside this tool, not automated by it in this version.
- Reconciliation compares current live data on both sides at run time; it is not expected to reconstruct historical point-in-time state.
- A single operator/no-auth model applies here as elsewhere in this system (per the existing project Assumptions); this feature does not introduce multi-user access control.

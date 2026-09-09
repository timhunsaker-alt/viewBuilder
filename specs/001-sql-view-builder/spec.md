# Feature Specification: Visual SQL Server View/Mapping Builder

**Feature Branch**: `001-sql-view-builder`

**Created**: 2026-09-09

**Status**: Draft

**Input**: User description: "Build viewBuilder: a visual tool for mapping legacy MS SQL Server tables to new tables/views. Users select a legacy source table, drag-link source columns to where the data should live in a new table/view, translate enum-coded columns to their values, and mark retired rows without mutating the source — instead writing an auditable retirement record. Users can dry-run a mapping before executing it for real, and executed runs are logged. Mapping and enum-translation definitions are saved, versioned, and reusable."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Map a legacy table to a new table visually (Priority: P1)

A data engineer picks a legacy source table from the connected SQL Server instance and, on a
visual canvas, drags links from each source column to the column it should populate on a
target table or view. They save this as a named, versioned mapping definition they can return
to and edit later.

**Why this priority**: This is the core value proposition of the tool — replacing hand-written,
one-off migration scripts with a visual, reviewable mapping. Nothing else in the system is
useful without it.

**Independent Test**: Can be fully tested by connecting to a test SQL Server database,
selecting a source table, drawing at least one column-to-column link, saving the mapping, and
confirming it can be reopened with the same links intact.

**Acceptance Scenarios**:

1. **Given** a connected SQL Server instance with a legacy table, **When** the user selects
   that table as the source, **Then** the tool displays all of its columns with their names
   and data types.
2. **Given** a source table's columns are displayed alongside a chosen target table/view's
   columns, **When** the user drags a link from a source column to a target column, **Then**
   the tool records that column-to-column mapping and displays the link on the canvas.
3. **Given** an in-progress mapping, **When** the user saves it, **Then** the mapping is
   persisted with a name and a version identifier and can be reopened later showing the same
   links.
4. **Given** a saved mapping is reopened, **When** the user changes a link and saves again,
   **Then** a new version of the mapping is created without altering the previously saved
   version.

---

### User Story 2 - Translate enum-coded columns to their real values (Priority: P1)

While mapping a source column that stores a small numeric/code value whose meaning is defined
elsewhere (an enum), the user selects or confirms which enum-translation table applies, so
that when the mapping runs, the target receives the human-readable value instead of the raw
code.

**Why this priority**: Several legacy tables encode meaning as enum codes; without table-driven
translation, migrated data would carry raw codes an end user cannot interpret, or worse, an
engineer would hardcode a private lookup that silently drifts out of sync.

**Independent Test**: Can be fully tested by mapping a known enum-coded source column, attaching
an enum-translation table with a few code→value entries, running the mapping in dry-run, and
confirming the preview shows translated values rather than raw codes.

**Acceptance Scenarios**:

1. **Given** a source column is flagged or recognized as enum-coded, **When** the user maps it
   to a target column, **Then** the tool prompts the user to attach an enum-translation table
   for that column.
2. **Given** an enum-translation table with entries for known codes, **When** a dry-run or
   execution encounters a code present in the table, **Then** the target receives the
   corresponding translated value.
3. **Given** an enum-translation table is missing an entry for a code found in the source data,
   **When** a dry-run or execution processes that row, **Then** the tool flags that row as
   untranslatable and does not guess, default, or silently drop the value.
4. **Given** an enum-translation table, **When** the user edits its entries and saves,
   **Then** a new version of the translation table is created, and mapping runs record which
   version they used.

---

### User Story 3 - Mark a row retired with a full audit trail (Priority: P1)

When a source row represents something that is "retired" — a status that today lives as an
enum code on the source row — the user runs the retirement mapping, and the tool writes a new
record to a retirement audit/history table capturing the row's identity, the translated
retirement reason, the timestamp, and the mapping version used. The original source row is
left untouched.

**Why this priority**: Retirement history is itself a record that must be trustworthy and
traceable. Treating retirement as a destructive update on the source row would make it
impossible to answer "what happened and when" after the fact — this is a core safety
requirement of the tool, equally load-bearing as the mapping feature it depends on.

**Independent Test**: Can be fully tested by running a retirement mapping against a source row
with a known retirement-status code, then confirming (a) the source row is byte-for-byte
unchanged, and (b) a new row exists in the retirement audit table with the correct identity,
translated reason, timestamp, and mapping version.

**Acceptance Scenarios**:

1. **Given** a source table with rows carrying a retirement-status enum code, **When** the user
   configures and runs a retirement mapping, **Then** the tool writes one new record per
   retired row into the retirement audit table.
2. **Given** a retirement audit record is written, **When** the user inspects it, **Then** it
   shows the retired row's identity, the human-readable retirement reason, the retirement
   timestamp, and the mapping version that produced it.
3. **Given** a row has already been retired once, **When** the same retirement mapping is run
   again over the same source data, **Then** the tool does not silently create a duplicate
   retirement record for that row (it is flagged or skipped, per the row's existing audit
   history).
4. **Given** a retirement mapping has run, **When** the user inspects the original source row,
   **Then** it is unchanged from before the run — no update, delete, or flag was set on it.

---

### User Story 4 - Preview a mapping with dry-run before touching real data (Priority: P2)

Before executing a mapping for real, the user runs it in dry-run/preview mode and sees exactly
what would be read from the source, how enum values would translate, what would be written to
the target and retirement audit tables, and row counts — all without writing anything.

**Why this priority**: This is what makes execution against a real legacy database safe enough
to trust; it depends on Stories 1–3 already working (there must be a mapping and translations
to preview) but is not itself required to prove the core mapping concept.

**Independent Test**: Can be fully tested by taking a saved mapping with a known small source
table, running dry-run, and confirming the preview's row counts and sample translated rows
match what would be produced by manually inspecting the source data.

**Acceptance Scenarios**:

1. **Given** a saved mapping, **When** the user runs dry-run, **Then** the tool reports the
   number of source rows read, the number of rows that would be written to the target, the
   number of retirement records that would be created, and the number of rows flagged as
   untranslatable.
2. **Given** a dry-run has completed, **When** the user reviews the results, **Then** they can
   see a sample of individual rows showing source values alongside their translated/mapped
   target values.
3. **Given** a dry-run is in progress or complete, **When** the user checks the target and
   retirement audit tables, **Then** no rows have actually been written to them.

---

### User Story 5 - Execute a mapping and get an auditable run log (Priority: P2)

Once satisfied with a dry-run, the user executes the mapping for real. The tool performs the
reads, translations, and writes, and produces a run log recording the mapping version used,
row counts, start/end timestamps, and the operator who ran it, so the run can be audited or
reconstructed later.

**Why this priority**: This is the payoff step; it depends on dry-run existing first so that
execution is never the first time a mapping is actually tried.

**Independent Test**: Can be fully tested by executing a mapping against a test database and
confirming both that the target/retirement tables contain the expected rows and that a run log
entry exists with matching counts, mapping version, and timestamp.

**Acceptance Scenarios**:

1. **Given** a mapping has been dry-run and reviewed, **When** the user chooses to execute it,
   **Then** the tool performs the reads, enum translations, and writes to the target and
   retirement audit tables as previewed.
2. **Given** an execution completes, **When** the user views the run history, **Then** they see
   an entry with the mapping name and version, source row count, target rows written,
   retirement records written, start and end time, and the operator.
3. **Given** an execution encounters a row with an untranslatable enum code, **When** that row
   is reached, **Then** the tool does not write a guessed/default value for it — it records the
   row as skipped/flagged in the run log and continues with the remaining rows (or halts,
   per configured mapping behavior), matching what dry-run predicted.

---

### Edge Cases

- What happens when the target table/view or a mapped target column does not exist or is
  dropped after the mapping was saved? The tool must detect this before execution (surfaced in
  dry-run) rather than failing mid-write.
- What happens when a source table's schema changes (a mapped column is renamed, dropped, or
  its type changes) after a mapping was saved? The tool must detect the mismatch and flag the
  mapping as needing review rather than running against a stale assumption.
- How does the system handle a source column mapped to a target column of an incompatible data
  type (e.g., text into a numeric target)? Flagged at mapping-save time and re-checked at
  dry-run/execution time; incompatible rows are not silently truncated or coerced.
- What happens if a migration run is interrupted partway through (connection loss, process
  crash)? The run log must reflect a partial/failed state, and re-running must not produce
  duplicate target or retirement rows for the portion that already completed.
- What happens when the user attempts to connect to a database explicitly flagged as
  production? The tool requires an explicit extra confirmation and still defaults to dry-run
  first.
- What happens when two mapping versions are run against overlapping source data? Each
  executed run is logged independently with its own mapping version, so downstream review can
  tell which version produced which rows.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST connect to a configured SQL Server instance and let the user browse
  and select an existing source table, displaying its columns, data types, and a data preview.
- **FR-002**: System MUST let the user select or specify a target table/view and display its
  columns and data types alongside the source table's columns on a visual canvas.
- **FR-003**: System MUST let the user create a column-to-column mapping by drawing a link
  between a source column and a target column on the canvas, and MUST let the user remove or
  redraw a link.
- **FR-004**: System MUST let the user save a set of column mappings as a named mapping
  definition, and MUST persist a new version each time a saved mapping definition is
  meaningfully edited and re-saved, without overwriting or losing prior versions.
- **FR-005**: System MUST let the user identify a mapped source column as enum-coded and
  attach an enum-translation table (a set of code→value entries) to that column's mapping.
- **FR-006**: System MUST let the user create, edit, and version enum-translation tables
  independently of any single mapping, and reuse a given translation table across multiple
  mappings.
- **FR-007**: System MUST, when running a mapping (dry-run or execution) that includes an
  enum-translated column, replace each source code with its translated value from the
  attached translation table's version recorded on the mapping.
- **FR-008**: System MUST flag, rather than guess/default/drop, any row whose enum code has no
  matching entry in the attached translation table, in both dry-run and execution.
- **FR-009**: System MUST let the user configure a "retirement" mapping that reads a source
  table's existing retirement-status enum column and, for rows meeting the retirement
  condition, writes a new record to a designated retirement audit/history table — and MUST
  NOT update or delete the source row as part of this operation.
- **FR-010**: System MUST record, for every retirement audit entry, the retired row's identity,
  its translated retirement reason, the retirement timestamp, and the mapping version that
  produced it.
- **FR-011**: System MUST prevent a repeated run of the same retirement mapping over already-
  retired rows from creating duplicate retirement audit entries for the same row.
- **FR-012**: System MUST let the user run any saved mapping in a dry-run/preview mode that
  reports row counts (read, would-write, would-retire, flagged/untranslatable) and a sample of
  individual rows with their source and translated/mapped values, and that performs no writes
  to the target or retirement audit tables.
- **FR-013**: System MUST let the user execute a saved mapping for real, performing the reads,
  enum translations, and writes to the target and retirement audit tables.
- **FR-014**: System MUST record a run log entry for every dry-run and every execution,
  capturing the mapping name and version, translation table version(s) used, row counts,
  start/end timestamps, the operator, and the run's outcome (completed, partially completed,
  failed).
- **FR-015**: System MUST detect, before an execution proceeds, whether the source or target
  schema referenced by a saved mapping has changed since the mapping was saved (missing
  table/column, or incompatible data type) and MUST block execution with a clear message
  rather than failing mid-write.
- **FR-016**: System MUST distinguish between at least a development/test environment and a
  production environment via explicit configuration, and MUST require an explicit additional
  confirmation before executing (not dry-running) a mapping against a database flagged as
  production.
- **FR-017**: System MUST make every saved mapping definition and enum-translation table
  viewable and editable later, including its full version history.

### Key Entities

- **Source Table Connection**: A reference to a specific table in a specific SQL Server
  database/environment that mappings read from; includes the table's introspected column
  names and data types.
- **Target Table/View**: A reference to the destination table or view a mapping writes to;
  includes its introspected column names and data types.
- **Mapping Definition**: A named, versioned set of source-column → target-column links,
  optionally referencing an enum-translation table per enum-coded column, plus retirement
  configuration if the mapping is a retirement mapping.
- **Enum Translation Table**: A named, versioned set of code → translated-value entries,
  reusable across multiple mapping definitions.
- **Retirement Audit Record**: An append-only record capturing a retired row's identity,
  translated retirement reason, retirement timestamp, and the mapping version that produced it.
- **Run Log Entry**: A record of one dry-run or execution of a mapping definition, capturing
  mapping/translation versions used, row counts, timestamps, operator, and outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from selecting a legacy source table to a saved, reusable mapping
  definition with at least one enum translation attached in under 15 minutes, without writing
  any SQL or hand-edited config by hand.
- **SC-002**: 100% of retirements performed through the tool produce a corresponding audit
  record, and 0% result in a modified or deleted source row, verified by comparing source data
  before and after any retirement run.
- **SC-003**: Every row written to a target table or the retirement audit table by an execution
  can be traced back to the exact mapping version, translation table version, and run log
  entry that produced it.
- **SC-004**: 100% of executions against a database flagged as production are preceded by a
  dry-run of the same mapping version and an explicit production confirmation step; 0% skip
  straight from mapping edit to production execution.
- **SC-005**: For a source column with an incomplete enum-translation table, 100% of
  untranslatable rows are visibly flagged in both dry-run and execution output, with 0% written
  as a guessed, defaulted, or blank value.
- **SC-006**: A user can reconstruct, from run logs alone (without inspecting the database
  directly), what a given execution changed — how many rows, of what kind, using which mapping
  and translation versions.

## Assumptions

- A single trusted internal operator uses the tool for this initial version; there is no
  multi-user authentication/authorization scheme yet, though the design should not preclude
  adding one later.
- Target tables/views already exist in the target database with a fixed schema; the tool does
  not create or alter target schema — it only reads/writes rows into what already exists.
- Only Microsoft SQL Server is supported as both source and target in this version; other
  database engines are out of scope.
- "Enum-coded" columns are identified by the user during mapping (the tool does not attempt to
  automatically infer which columns are enums from data alone).
- A row's identity for retirement/audit purposes is its source table's existing primary key (or
  an equivalent unique key the user designates when configuring the mapping).
- Mapping and translation-table definitions, retirement audit records, and run logs are stored
  in a dedicated application datastore (separate from the legacy source database), so that the
  tool's own metadata never depends on write access to legacy tables beyond the mapped
  target/audit tables.

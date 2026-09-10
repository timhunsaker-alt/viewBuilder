# Phase 0 Research: Legacy-Shape Compatibility View & Reconciliation

## 1. Reading legacy XML: server-side pushdown vs. client-side parsing

**Decision**: Use SQL Server's native `xml` column type and push extraction down as plain
T-SQL via SQLAlchemy `text()`: `SELECT xml_col.value('(/Application/CollateralValue)[1]',
'NVARCHAR(200)') FROM xml_documents WHERE id = :id`. The XML field mapping stores an
XPath-like expression (plus a target SQL type for the `.value()` cast) per old-table
column.

**Rationale**: SQL Server has supported native `xml` columns with `.value()`/`.query()`
XPath methods since SQL Server 2005; pushing the extraction down avoids pulling
potentially large XML documents over the wire into Python just to parse one field, and
keeps the "three distinct outcomes" requirement (FR-012: found / document-exists-field-
missing / document-not-found) cheap to compute in one round trip: a NULL result from
`.value()` combined with a separate `EXISTS` check on the identity distinguishes all three
cases without fetching the document body at all.

**Alternatives considered**: Pull the full XML document into Python and parse with
`lxml`/`ElementTree` (rejected as the default: adds a dependency, pulls potentially large
payloads over the network merely to read one field, and reimplements XPath evaluation
that SQL Server already provides — however, research.md flags this as a fallback worth
revisiting in plan/tasks if the legacy XML turns out not to be stored in a native `xml`
column, e.g. if it's actually `NVARCHAR(MAX)`/`TEXT`, in which case `.value()` still works
via `CAST(col AS XML)` inline, so no separate library is needed even then).

## 2. Reconciliation comparison strategy at scale

**Decision**: Row-level comparison keyed by the user-designated identity column, computed
as: (a) a set-difference on identity values between old table and view to find old-only /
view-only rows, then (b) for identities present on both sides, a per-column value compare
driven by the same column list captured in the Legacy Shape Capture — pushed down as a
single SQL query per side (`SELECT * FROM old_table ORDER BY id` / `SELECT * FROM view
ORDER BY id`) streamed and compared in the backend rather than pulled entirely into
memory at once, chunked by identity-value ranges for tables large enough to matter
(threshold decided in tasks.md, not hard-coded here).

**Rationale**: This directly serves FR-009's three required outputs (old-only, view-only,
column-mismatch counts+detail) with a single pass per side per chunk, and streaming/
chunking is what makes the 100k-row / 5-minute performance goal realistic without loading
an entire wide table into backend memory at once.

**Alternatives considered**: A single outer-join SQL query computing the diff entirely
inside SQL Server (rejected as the default: the old table and the new-schema view may not
always be reachable via the same connection per spec edge cases, so a query that assumes
both are queryable in one FROM clause doesn't generalize; the backend-side streaming
compare works whether both sides are on the same connection or not). Hashing entire rows
instead of comparing column-by-column (rejected: FR-009 requires per-column mismatch
detail, not just "this row differs somehow" — a hash comparison would need a second pass
to explain which column differed anyway).

## 3. XML "field not found" vs. Constitution Principle III's enum-translation model

**Decision**: The XML fallback lookup treats its three outcomes (found / document-exists-
field-missing / document-not-found) as its own first-class result type, not shoehorned
into the existing `EnumTranslationTable` model from 001 — an XML field mapping is a
location (XPath + type), not a finite code→value table.

**Rationale**: Constitution Principle III is specifically about "never silently guess/
default an untranslated enum code"; the XML lookup's job is different (find whether a
value exists at all, for human investigation), so forcing it through the enum-translation
data shape would misrepresent what's actually being modeled. The versioning discipline
(Principle II) still applies to the field-mapping *configuration* (which XPath is used
for which column) — that part is directly analogous.

**Alternatives considered**: Reusing `EnumTranslationTable`'s code→value shape with the
XPath-as-"code" and a placeholder "value" (rejected: conflates two different concepts —
enum translation is "map a known code to its meaning," XML lookup is "search a document
for a possibly-absent field" — and would make the three-outcome distinction from FR-012
awkward to express in a table meant for exact-match code lookups).

## 4. Multi-table join-graph model for the canvas

**Decision**: Model the join graph as an explicit list of edges (`{left_table, left_column,
right_table, right_column, join_type}`), validated at save time (every selected table must
be reachable from at least one other via some chain of edges — no orphan tables), and
rendered on the canvas as connections between table-level nodes, distinct from the
column-level links used for the final old-column → source-expression mapping (which reuses
001's `MappingCanvas` interaction once the join graph is fixed).

**Rationale**: This directly serves FR-002 (configure joins, validate reachability) and
keeps the two concerns — "how do the new tables relate to each other" vs. "which old
column comes from which new-schema value" — visually and data-model distinct, matching how
a person would actually think through building this view.

**Alternatives considered**: Requiring the user to write the join conditions as raw SQL
(rejected: defeats the purpose of a visual tool, and the whole point of this feature is
letting a non-SQL-fluent reviewer see and validate the shape); inferring joins
automatically from foreign-key metadata (rejected as the default: the new schema may not
have FK constraints declared even where a real relationship exists — legacy-adjacent
schemas are exactly where this is common — so auto-inference can't be relied on, though a
future enhancement could offer it as a suggestion).

## 5. Old-table-name collision with the deployed view

**Decision**: Confirmed by spec Assumptions — the tool deploys the view under its own
distinct name (e.g. a name the user provides, validated to not equal the captured legacy
table's name) for the entire lifetime of this feature's scope. No code path attempts to
rename or drop the old table.

**Rationale**: SQL Server cannot have a table and a view with the same name in the same
schema simultaneously; the actual cutover (retiring the old table, renaming/repointing the
view or reports) is an irreversible, high-consequence action on a live legacy asset that
belongs in a deliberate, human-reviewed runbook step — not something this tool automates,
consistent with Constitution Principle I's bias toward reviewable, reversible steps.

**Alternatives considered**: Automating the rename/cutover as a guarded, confirmed
operation within the tool (rejected for this version: out of scope per spec Assumptions;
revisit only if a future spec explicitly asks for it after this feature has been in
production use).

## 6. Windows authentication for `connection_config`: per-user delegation vs. service account

**Decision**: `connection_config.auth_mode` supports exactly two values: `sql` (a stored
SQL Server login, unchanged from 001) and `windows_integrated` — the ODBC driver's own
`Trusted_Connection=yes` path, authenticating as the backend process's **single, fixed
Windows/AD service-account identity**. There is no per-end-user delegation: every operator
using a `windows_integrated` connection authenticates to SQL Server as the same service
account, and per-action attribution is carried entirely by the existing `operator` field
recorded in the structured audit log (`backend/src/api/middleware.py::log_audit_event`),
not by the SQL Server connection identity itself.

**Rationale**: True per-user Kerberos constrained delegation (S4U2Proxy) — where the
backend authenticates to SQL Server *as the actual logged-in operator*, not as itself —
requires the backend host to hold a Kerberos service ticket obtained on that specific
user's behalf, which in turn requires either (a) the operator authenticating to the
backend itself via Kerberos/SPNEGO (browser → IIS/Windows-auth middleware → constrained
delegation), or (b) a domain-joined Windows/.NET component fronting the SQL connection,
since constrained delegation is a Windows/AD protocol concept with no equivalent in
`pyodbc`/unixODBC/FreeTDS running on Linux. This sandbox and this backend's deployment
target (Linux containers on Docker Swarm, per `deploy/stack.yml`) have neither a
domain-joined host nor a Windows-auth-capable front door, so a per-user delegation path
could not be built here in a way that could actually be verified end-to-end — building
unverifiable plumbing that silently falls back to something else on failure would violate
Constitution Principle III's "no silent guessing" spirit applied to authentication
identity. A fixed service-account identity, by contrast, is exactly what
`Trusted_Connection=yes` already gives a domain-joined Linux/pyodbc host without any
additional infrastructure, and per-operator accountability is preserved through the audit
log rather than through the database connection identity — consistent with how `sql`-mode
connections already work today (one shared `credential_ref`, with the human operator
recorded separately).

**Alternatives considered**: True per-user Kerberos constrained delegation (rejected: not
buildable or verifiable from this Python/Linux backend without a Windows/.NET delegation
component this project does not have); requiring users to enter their own Windows
credentials per-session for SQL auth instead (rejected: reintroduces the exact
credential-handling surface `windows_integrated` mode exists to avoid, and the spec's
`sql` mode already covers the "distinct login per connection" case).

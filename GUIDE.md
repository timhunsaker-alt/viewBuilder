# viewBuilder operator guide

viewBuilder helps teams move from a legacy SQL Server schema to a replacement schema without
losing the ability to validate the result. It has two related workflows:

- **Table mappings** copy data from a selected source table to a selected target table or view.
  They support enum-code translation, a no-write preview, execution history, and an append-only
  retirement audit.
- **Compatibility views** reproduce the column shape of an old wide table from normalized
  replacement tables. They can be previewed, deployed, reconciled with the old table, and checked
  against legacy XML when a replacement value is missing.

## Start the application

### Local services

Start the sample SQL Server and the metadata database:

```bash
cd backend/docker
docker compose up -d
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn src.api.main:app --reload --port 8000
```

For a local metadata database without Docker, set
`METADATA_DATABASE_URL="sqlite:///./viewbuilder.db"` before starting the backend. The
application creates its metadata schema on startup for this SQLite option.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend sends API requests to the backend at port 8000.

## Navigation

The top menu is available on every page.

- **Home** starts a table-mapping flow by choosing a connection and source table.
- **Build** opens compatibility views, starts a legacy-shape capture, or returns to source-table
  selection.
- **Manage** contains connections, enum translations, and run history.

On compact screens, select **Menu** to open the same navigation.

## Connect to SQL Server

1. Open **Manage → Connections**.
2. Enter a descriptive name, environment, SQL Server host, port, and database.
3. Choose **SQL Login** and supply a username plus server-side credential reference, or choose
   **Windows Integrated** when the backend host has the appropriate domain identity.
4. Save the connection.

The application retains the credential reference, not a password returned to the browser.

## Create and run a table mapping

1. On **Home**, choose a connection and then a source table.
2. Select **Continue to mapping canvas**.
3. Name the mapping and choose its target connection and target table or view.
4. Draw links from source columns to their destination columns.
5. If a source column contains codes, create or select an enum translation table under
   **Manage → Enum translations**, then attach it to the relevant link.
6. Save the mapping, then select **Run dry run**. Review row counts and sample output.
7. Select **Execute for real** only after the preview is correct.

Production-tagged connections require a separate confirmation before execution. Every preview and
execution is recorded under **Manage → Run history**.

### Record a retirement

From the source-table screen, select **Configure retirement mapping**. Choose the source identity
and status columns, the retirement codes, and the target audit columns. Executing this mapping
adds audit records; it does not alter the source rows.

## Build a compatibility view

1. Choose **Build → Capture legacy shape**. Select the old table and save a snapshot of its
   column names, order, types, and nullability.
2. Choose **Build → Compatibility views**, then select **Create compatibility view**.
3. Name the view, select the captured shape, and select the connection containing the normalized
   replacement tables.
4. Select every required replacement table and connect them on the join graph.
5. Map every old column to a source column or expression. Mark a column **Retired** only when it
   intentionally has no live source; the deployed view returns a typed `NULL` for it.
6. Save the definition. Open it later from **Build → Compatibility views** to create a newer
   version, inspect version SQL, preview, deploy, or reconcile.

### Preview and deploy

Previewing generates the SQL and sample rows without creating or changing a database object.
Deploying creates or updates the SQL Server view. A production connection requires confirmation.
When a deployment changes the output column shape, the application highlights added, removed, or
reordered columns.

### Reconcile and use XML fallback

After deployment, select **Reconcile against the old table** and choose an identity column. The
result reports matched rows, rows found on only one side, duplicate view rows caused by join
inflation, and individual column mismatches.

For a discrepancy that may exist only in a legacy XML document, open its XML lookup action.
Configure the XML source once through `POST /api/v1/xml-field-mappings` with the XML table,
identity column, and payload column. In the UI, select that mapping, add the XPath for the legacy
column, and run the lookup. Results distinguish a found value, a missing field, and a missing
document.

## How safety and history work

- A preview only reads data; it does not write table rows or deploy a view.
- Saving a mapping, compatibility view, translation table, or XML mapping creates a new version.
  Earlier versions remain available for review.
- Unknown enum codes are flagged rather than guessed.
- Retirement writes are append-only audit records.
- Deployments and mapping runs include an operator, outcome, generated SQL where applicable, and
  relevant counts or differences.

## Verify a local change

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/black --check .

cd ../frontend
npm run test
npm run build
npm run lint
```

Live SQL Server coverage runs when the seeded MSSQL container and an ODBC driver are available.

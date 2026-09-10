"""Standalone, read-only reconciliation check — no Docker, no Postgres metadata
store, no FastAPI server. Connects directly to a SQL Server instance using Windows
Integrated Security (the caller's own domain identity, `Trusted_Connection=yes`) and
compares a legacy table against an already-deployed compatibility view, reusing the
same pure comparison logic as the full app (`src.services.reconciliation_engine`).

Built for the case where the view was deployed by someone else (an admin with
CREATE VIEW rights) and you only have — and only want — SELECT access: this script
never issues anything but SELECT against either table, and never touches Postgres,
Docker, or the FastAPI backend at all.

Usage (works from any directory — the script locates `src` relative to itself):

    python scripts/local_reconcile.py ^
        --server sql.corp.example.com --database LoanServicing ^
        --old-table dbo.legacy_loan_application ^
        --view dbo.compat_legacy_loan_application ^
        --identity-column application_id ^
        --retired-columns collateral_type,collateral_description

Requires only `sqlalchemy` and `pyodbc` (see the module docstring in
`src/connectors/mssql.py` for why the ODBC string is shaped this way) plus the
Microsoft "ODBC Driver 18 for SQL Server" installed on this machine — no other
part of this repo's dependency list (FastAPI, Postgres driver, Alembic, ...) is
needed to run this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.reconciliation_engine import compare_row_sets  # noqa: E402


def _json_safe(value):
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _json_safe_row(row: dict) -> dict:
    return {k: _json_safe(v) for k, v in row.items()}


def build_windows_auth_engine(server: str, port: int, database: str, driver: str):
    odbc_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        "TrustServerCertificate=yes;"
        "Trusted_Connection=yes;"
    )
    connection_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_str)}"
    return create_engine(connection_url, pool_pre_ping=True, future=True)


def _split_schema_table(qualified_name: str) -> tuple[str | None, str]:
    schema, _, table = qualified_name.partition(".")
    if not table:
        return None, schema
    return schema, table


def fetch_rows(engine, table: str, identity_column: str) -> list[dict]:
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT * FROM {table} ORDER BY {identity_column}"))
        return [_json_safe_row(dict(row)) for row in result.mappings().all()]


def infer_columns(engine, table: str) -> list[str]:
    schema, table_name = _split_schema_table(table)
    inspector = inspect(engine)
    return [c["name"] for c in inspector.get_columns(table_name, schema=schema)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only reconciliation: compares a legacy table against an already-"
            "deployed compatibility view over Windows Integrated Security. Never "
            "issues anything but SELECT."
        )
    )
    parser.add_argument("--server", required=True, help="SQL Server hostname")
    parser.add_argument("--port", type=int, default=1433)
    parser.add_argument("--database", required=True)
    parser.add_argument(
        "--old-table", required=True, help="Schema-qualified legacy table, e.g. dbo.legacy_x"
    )
    parser.add_argument(
        "--view", required=True, help="Schema-qualified deployed view, e.g. dbo.compat_x"
    )
    parser.add_argument("--identity-column", required=True)
    parser.add_argument(
        "--columns",
        help="Comma-separated columns to compare (default: every column on --old-table)",
    )
    parser.add_argument(
        "--retired-columns",
        default="",
        help=(
            "Comma-separated legacy columns the view deliberately casts to NULL "
            "(column_status='Retired'). A NULL view-side value for one of these "
            "is never compared against the old table's value — ask whoever "
            "deployed the view for this list, or check its legacy_view_column_rule "
            "rows if you have access to the metadata store."
        ),
    )
    parser.add_argument(
        "--driver",
        default="ODBC Driver 18 for SQL Server",
        help="Installed ODBC driver name (try 'ODBC Driver 17 for SQL Server' if 18 isn't there)",
    )
    parser.add_argument(
        "--output",
        default="reconcile_result.json",
        help="Where to write the full discrepancy detail as JSON",
    )
    args = parser.parse_args()

    engine = build_windows_auth_engine(args.server, args.port, args.database, args.driver)

    compare_columns = (
        [c.strip() for c in args.columns.split(",") if c.strip()]
        if args.columns
        else infer_columns(engine, args.old_table)
    )
    retired_columns = {c.strip() for c in args.retired_columns.split(",") if c.strip()}

    print(f"Reading {args.old_table} ...")
    old_rows = fetch_rows(engine, args.old_table, args.identity_column)
    print(f"Reading {args.view} ...")
    view_rows = fetch_rows(engine, args.view, args.identity_column)

    result = compare_row_sets(
        old_rows=old_rows,
        view_rows=view_rows,
        identity_column=args.identity_column,
        compare_columns=compare_columns,
        retired_columns=retired_columns,
    )

    print()
    print(f"rows_matched:              {result.rows_matched}")
    print(f"rows_old_only:             {result.rows_old_only}")
    print(f"rows_view_only:            {result.rows_view_only}")
    print(f"rows_with_column_mismatch: {result.rows_with_column_mismatch}")
    print(f"row_inflation_flagged:     {result.row_inflation_flagged}")

    Path(args.output).write_text(json.dumps(result.discrepancy_detail, indent=2, default=str))
    print(f"\nFull discrepancy detail written to {args.output}")

    has_discrepancies = (
        result.rows_old_only or result.rows_view_only or result.rows_with_column_mismatch
    )
    return 1 if has_discrepancies else 0


if __name__ == "__main__":
    raise SystemExit(main())

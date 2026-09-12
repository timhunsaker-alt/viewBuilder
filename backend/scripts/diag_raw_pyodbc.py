"""Diagnostic: raw pyodbc.connect() with no SQLAlchemy/app code involved at all.
Edit HOST/DATABASE below, then run:  python scripts\\diag_raw_pyodbc.py
"""

import pyodbc

HOST = "YOUR_SERVER_HOST"
DATABASE = "YOUR_DATABASE"

conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={HOST},1433;"
    f"DATABASE={DATABASE};"
    "TrustServerCertificate=yes;"
    "Trusted_Connection=yes;"
)
print(conn_str)
conn = pyodbc.connect(conn_str)
print("connected OK")

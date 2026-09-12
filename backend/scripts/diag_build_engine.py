"""Diagnostic: build a connection exactly the way the app does and try to connect.
Edit HOST/DATABASE below, then run:  python scripts\\diag_build_engine.py
(works from any working directory — the sys.path line below locates `src` relative
to this file, since Python only auto-adds the script's own folder, not backend/).
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.connectors.mssql import build_engine  # noqa: E402
from src.models.connection_config import ConnectionConfig  # noqa: E402

HOST = "YOUR_SERVER_HOST"
DATABASE = "YOUR_DATABASE"

c = ConnectionConfig(
    id=uuid.uuid4(),
    name="diag",
    role="either",
    environment="dev",
    host=HOST,
    port=1433,
    database=DATABASE,
    auth_mode="windows_integrated",
    username=None,
    credential_ref=None,
)
engine = build_engine(c)
print(engine.url)
with engine.connect() as conn:
    print("connected OK")

#!/usr/bin/env bash
set -euo pipefail

echo "waiting for metadata store..."
python - <<'PY'
import time
import sys
from sqlalchemy import create_engine, text
from src.settings import settings

engine = create_engine(settings.metadata_database_url)
for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception as exc:  # noqa: BLE001
        print(f"metadata store not ready yet ({exc.__class__.__name__}), retrying...")
        time.sleep(2)
else:
    print("metadata store never became reachable", file=sys.stderr)
    sys.exit(1)
PY

echo "running alembic migrations..."
alembic upgrade head

# Optional: seed a legacy MS SQL Server with the sample banking schema. Only runs when
# SEED_MSSQL_HOST is set (the Portainer test deployment sets it; normal use of this image
# does not) — this container already ships sqlcmd + the seed script for exactly that case.
if [ -n "${SEED_MSSQL_HOST:-}" ]; then
    echo "waiting for legacy MS SQL Server at ${SEED_MSSQL_HOST}..."
    for i in $(seq 1 30); do
        if sqlcmd -C -S "${SEED_MSSQL_HOST}" -U sa -P "${SEED_MSSQL_SA_PASSWORD}" -Q "SELECT 1" >/dev/null 2>&1; then
            break
        fi
        echo "  not ready yet, retrying..."
        sleep 5
    done
    echo "seeding legacy MS SQL Server..."
    sqlcmd -C -S "${SEED_MSSQL_HOST}" -U sa -P "${SEED_MSSQL_SA_PASSWORD}" -i /app/docker/mssql-init/seed.sql
fi

echo "starting API server..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000

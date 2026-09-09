FROM python:3.12-slim-bookworm

# Microsoft ODBC Driver 18 for SQL Server + unixodbc, required by pyodbc at runtime
# (this is the exact driver missing from the local dev sandbox, per research.md §1).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg2 ca-certificates \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 mssql-tools18 unixodbc-dev \
    && apt-get purge -y --auto-remove curl gnupg2 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/mssql-tools18/bin:${PATH}"

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
# requirements-dev.txt (pytest/ruff/black) is intentionally included in the test image so
# the deployed container can run the real test suite against a live MS SQL Server —
# this is a test deployment, not a hardened production image.
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY src ./src
COPY tests ./tests
COPY db ./db
COPY alembic.ini ./alembic.ini
COPY docker/mssql-init ./docker/mssql-init
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]

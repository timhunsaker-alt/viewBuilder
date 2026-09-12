from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    metadata_database_url: str = (
        "postgresql+psycopg://viewbuilder:viewbuilder_dev@localhost:5434/viewbuilder_metadata"
    )
    dry_run_sample_size: int = 20
    # The installed Microsoft ODBC driver name for reaching SQL Server sources/targets
    # (distinct from metadata_database_url, which is only ever Postgres/SQLite). Defaults
    # to 17 since that's what a plain local machine is more likely to already have (a
    # locked-down work machine especially); the Docker image installs 18, so
    # deploy/stack.yml overrides MSSQL_ODBC_DRIVER back to 18 explicitly for that
    # deployment rather than relying on this default.
    mssql_odbc_driver: str = "ODBC Driver 17 for SQL Server"


settings = Settings()

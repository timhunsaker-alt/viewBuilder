from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    metadata_database_url: str = (
        "postgresql+psycopg://viewbuilder:viewbuilder_dev@localhost:5434/viewbuilder_metadata"
    )
    dry_run_sample_size: int = 20


settings = Settings()

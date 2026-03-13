from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # REQUIRED — no default. App fails fast at startup if DATABASE_URL is not set.
    # Never hardcode credentials as fallback defaults.
    database_url: str

    api_version: str = "1.1.0"
    api_title: str = "TonomitoSQL"
    api_description: str = "Molecular search API powered by PostgreSQL + RDKit"

    # Upload settings
    max_upload_size: int = 1_073_741_824  # 1GB in bytes — sufficient for ~3M row CSV

    # Server settings
    web_workers: int = 4  # Uvicorn worker count (override with WEB_WORKERS env var)

    # Logging
    log_level: str = "INFO"  # Override with LOG_LEVEL env var

    model_config = {"env_file": ".env"}


settings = Settings()

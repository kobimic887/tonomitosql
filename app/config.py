from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://tonomito:tonomito_dev@db:5432/tonomitosql"
    api_version: str = "0.1.0"
    api_title: str = "TonomitoSQL"
    api_description: str = "Molecular search API powered by PostgreSQL + RDKit"

    # Upload settings
    max_upload_size: int = 1_073_741_824  # 1GB in bytes — sufficient for ~3M row CSV

    model_config = {"env_file": ".env"}


settings = Settings()

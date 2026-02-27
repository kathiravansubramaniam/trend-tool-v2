from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str

    # GCS
    gcs_bucket_name: str
    gcs_project_id: str
    gcs_credentials_path: str = "./gcp/service-account-key.json"
    gcs_credentials_json: str = ""  # JSON string alternative to file (use on Railway/Vercel)

    # Models
    parse_model: str = "gpt-4o-mini"
    query_model: str = "gpt-4o"

    # Parsing
    max_concurrent_parses: int = 5
    max_parse_tokens: int = 8000

    # Paths
    local_pdf_cache: str = "./data/pdf_cache"
    index_db_path: str = "./data/index.db"

    # Trigger
    trigger_mode: str = "polling"
    polling_interval_seconds: int = 60

    # Query
    max_query_docs: int = 8
    max_context_tokens: int = 14000

    @property
    def pdf_cache_path(self) -> Path:
        return Path(self.local_pdf_cache)

    @property
    def db_path(self) -> Path:
        return Path(self.index_db_path)

    @property
    def credentials_path(self) -> Path:
        return Path(self.gcs_credentials_path)


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    QDRANT_URL: str
    QDRANT_API_KEY: str

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str | None = None

    MONGO_URI: str
    MONGO_DB: str

    PUBSUB_PROJECT_ID: str | None = None
    PUBSUB_CREDENTIALS_PATH: str | None = None
    DOC_STATUS_TOPIC: str = "doc-status"
    DOC_INGESTION_REQUEST_TOPIC: str = "doc-ingestion-requests"

    @property
    def FINAL_SUPABASE_KEY(self) -> str:
        return self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_KEY

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
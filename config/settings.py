from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 600
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str | None = None

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "rag"

    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_NAME: str = "postgres"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_SSLMODE: str = "verify-full"
    DB_SSLROOTCERT: str | None = r"certs\prod-ca-2021.crt"

    PUBSUB_PROJECT_ID: str | None = None
    PUBSUB_CREDENTIALS_PATH: str | None = None
    DOC_STATUS_TOPIC: str = "doc-status"
    DOC_INGESTION_REQUEST_TOPIC: str = "doc-ingestion-requests"

    @property
    def FINAL_SUPABASE_KEY(self) -> str:
        key = self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_KEY
        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY must be set")
        return key

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

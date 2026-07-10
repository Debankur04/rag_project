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

    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    @property
    def FINAL_SUPABASE_KEY(self) -> str:
        key = self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_KEY
        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY must be set")
        return key

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

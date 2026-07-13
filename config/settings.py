from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    APP_ENV: str = "production"
    ENABLE_TIMING: bool = False

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

    @property
    def TIMING_ENABLED(self) -> bool:
        return self.ENABLE_TIMING or self.APP_ENV.lower() in {
            "dev",
            "development",
            "local",
        }

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


settings = Settings()

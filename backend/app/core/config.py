
from typing import Optional
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings loaded from environment variables with defaults.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # LLM Parameters (Nebius Token Factory)
    LLM_PROVIDER: str = "nebius"
    NEBIUS_API_KEY: Optional[str] = None
    NEBIUS_BASE_URL: str = "https://api.tokenfactory.us-north1.nebius.com/v1/"
    NEBIUS_MODEL: str = "nvidia/Nemotron-3.5-Super-VL"
    NEBIUS_TIMEOUT_SECONDS: Optional[float] = None

    @field_validator("NEBIUS_TIMEOUT_SECONDS", mode="before")
    @classmethod
    def normalize_timeout(cls, value, info: ValidationInfo):
        if value is None or str(value).strip().lower() in {"", "none", "null"}:
            return None
        return value

    # Storage Settings
    POSTGRES_URL: str = "postgresql+asyncpg://postgres:123@127.0.0.1:5432/web_agent"
    POSTGRES_DATA_DIR: str = "./data/postgres_data"
    POSTGRES_CTL_PATH: str = "D:/postregSQL/bin/pg_ctl.exe"
    POSTGRES_LOG_PATH: str = "./data/postgres.log"
    POSTGRES_AUTO_START: bool = True
    POSTGRES_CONNECT_TIMEOUT_SECONDS: int = 5
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SERVICE_NAME: str = "Memurai"
    REDIS_AUTO_START: bool = True
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 5.0
    USE_REDIS_MEMORY_FALLBACK: bool = True
    GUEST_SESSION_TTL_SECONDS: int = 86400

    # Browser Execution Parameters
    BROWSER_HEADLESS: bool = False
    BROWSER_PERSISTENT_PROFILE: bool = True
    BROWSER_PROFILE_DIR: str = "./data/browser_profile"
    BROWSER_DEFAULT_START_URL: str = "https://www.google.com"
    BROWSER_REQUIRE_LOGIN_BEFORE_TASK: bool = True
    BROWSER_ELECTRON_CDP: bool = False
    BROWSER_CDP_URL: str = "http://127.0.0.1:9222"
    BROWSER_SLOW_MO_MS: int = 0
    MAX_TASK_STEPS: int = 100
    MAX_ACTION_RETRIES: int = 3
    MAX_SAME_STATE_REPETITIONS: int = 3
    ACTION_TIMEOUT_MS: int = 15000
    PAGE_LOAD_TIMEOUT_MS: int = 30000

    # RAG Settings
    RAG_ENABLED: bool = True
    PLAYWRIGHT_DOCS_PATH: str = "../playwright/docs"
    CHROMA_DB_DIR: str = "./data/chroma_db"
    RAG_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RAG_COLLECTION_NAME: str = "playwright_docs"
    RAG_TOP_K: int = 4


settings = Settings()

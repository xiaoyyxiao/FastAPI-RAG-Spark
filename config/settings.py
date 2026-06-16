from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_TITLE: str = "FastAPI RAG Spark"
    APP_VERSION: str = "1.0.0"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_EXPIRE_SECONDS: int = 600
    REDIS_SSL: bool = False

    SECRET_KEY: str = "change-this-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    XF_APPID: str = ""
    XF_APISecret: str = ""
    XF_APIKey: str = ""
    XF_DOMAIN: str = "lite"
    XF_MODEL: str = "lite"
    XF_URL: str = "https://spark-api-open.xf-yun.com/v1/chat/completions"
    LLM_PRIMARY_PROVIDER: str = "spark"
    LLM_FALLBACK_PROVIDER: str = "mock"
    LLM_REQUEST_TIMEOUT_SECONDS: int = 30

    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-zh"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS: list[str] = ["txt", "pdf", "docx"]


settings = Settings()

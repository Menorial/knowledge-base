from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    AI_API_KEY: str = ""
    AI_BASE_URL: str = "https://api.openai.com/v1"
    AI_MODEL: str = "gpt-4o-mini"
    AI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    DB_PATH: str = "data/knowledge.db"
    VECTOR_DIM: int = 512  # 默认匹配本地 BGE-small-zh-v1.5（512 维）；OpenAI 用 1536，通义用 1024

    FILE_STORAGE_DIR: str = "data/files"
    MAX_FILE_SIZE: int = 20 * 1024 * 1024
    ALLOWED_EXTENSIONS: str = ".md,.txt,.pdf,.docx,.html"

    BACKUP_DIR: str = "backup"
    BACKUP_KEEP_DAYS: int = 7

    # 本地 Embedding 模型下载（首次约 100MB）
    HF_ENDPOINT: str = "https://hf-mirror.com"
    BGE_OFFLINE: bool = False

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def db_abs_path(self) -> Path:
        p = BASE_DIR / self.DB_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def file_storage_abs(self) -> Path:
        p = BASE_DIR / self.FILE_STORAGE_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def backup_abs_path(self) -> Path:
        p = BASE_DIR / self.BACKUP_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",")}


settings = Settings()

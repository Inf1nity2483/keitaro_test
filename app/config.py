from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    keitaro_base_url: str = "https://tlgk.host"
    keitaro_api_key: str = ""
    campaign_prefix: str = ""
    keitaro_group_name: str = "FORTESTS"
    keitaro_source_name: str = "FORTESTS"
    keitaro_domain_id: int | None = None
    database_url: str = "postgresql+psycopg://keitaro:keitaro@localhost:5432/keitaro"

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("keitaro_base_url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("campaign_prefix", "keitaro_group_name", "keitaro_source_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("keitaro_domain_id", mode="before")
    @classmethod
    def empty_domain(cls, value):
        if value is None or value == "":
            return None
        return value

    @field_validator("database_url")
    @classmethod
    def absolute_sqlite(cls, value: str) -> str:
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value
        path = value[len(prefix) :]
        if path == ":memory:" or Path(path).is_absolute():
            return value
        full = (ROOT / path).resolve()
        return prefix + full.as_posix()


def get_settings() -> Settings:
    return Settings()


def sqlite_path(url: str) -> Path | None:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix) :]
    if raw == ":memory:":
        return None
    return Path(raw)


def ensure_sqlite_dir(url: str) -> None:
    path = sqlite_path(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

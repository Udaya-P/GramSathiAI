"""Fail-closed environment configuration; no default credentials."""
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.engine import make_url


DEFAULT_AUDIO_STORAGE_DIR = Path(__file__).resolve().parents[1] / ".recordings"


class Settings(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_minutes: int = Field(default=30, ge=1, le=60)
    cors_origins: list[str] = Field(default_factory=list)
    gnani_api_key: SecretStr | None = None
    audio_storage_dir: Path = DEFAULT_AUDIO_STORAGE_DIR
    groq_api_key: SecretStr | None = None
    groq_model: str = Field(default="llama-3.3-70b-versatile", min_length=1, max_length=200)
    app_environment: Literal["development", "test", "production"] = "production"
    enable_mock_reasoning: bool = False

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr) -> SecretStr:
        if make_url(value.get_secret_value()).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret.encode()) < 32 or "REPLACE" in secret.upper():
            raise ValueError("JWT_SECRET must be a generated secret of at least 32 bytes")
        return value

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path
                    or parsed.query or parsed.fragment or "*" in origin):
                raise ValueError("CORS_ORIGINS must contain exact http(s) origins without paths")
        return origins


@lru_cache
def get_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        jwt_secret=os.environ["JWT_SECRET"],
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_minutes=os.getenv("ACCESS_TOKEN_MINUTES", "30"),
        cors_origins=json.loads(os.getenv("CORS_ORIGINS", "[]")),
        gnani_api_key=os.getenv("GNANI_API_KEY") or None,
        audio_storage_dir=Path(os.getenv("AUDIO_STORAGE_DIR") or DEFAULT_AUDIO_STORAGE_DIR).expanduser(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip() or None,
        groq_model=os.getenv("GROQ_MODEL", "").strip() or "llama-3.3-70b-versatile",
        app_environment=os.getenv("APP_ENVIRONMENT", "production"),
        enable_mock_reasoning=os.getenv("ENABLE_MOCK_REASONING", "false"),
    )

"""
基础配置读取。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _set_env_if_missing(name: str, value: object) -> None:
    if value is None:
        return
    if os.getenv(name):
        return
    if isinstance(value, bool):
        os.environ[name] = "true" if value else "false"
    else:
        os.environ[name] = str(value)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


@dataclass
class LLMSettings:
    provider: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    openai_max_tokens: int
    openai_temperature: float
    openai_max_retries: int
    openai_timeout: float
    metadata_max_tokens: int
    metadata_temperature: float
    extraction_max_tokens: int
    extraction_temperature: float
    router_max_tokens: int
    router_temperature: float
    summary_max_tokens: int
    summary_temperature: float

    @classmethod
    def from_env(cls) -> "LLMSettings":
        return cls(
            provider=_env_str("LLM_PROVIDER", "openai"),
            openai_api_key=_env_str(
                "OPENAI_API_KEY_RUNTIME", _env_str("OPENAI_API_KEY", "")
            ),
            openai_base_url=_env_str(
                "OPENAI_BASE_URL_RUNTIME",
                _env_str("OPENAI_BASE_URL", ""),
            ),
            openai_model=_env_str(
                "OPENAI_MODEL_RUNTIME", _env_str("OPENAI_MODEL", "qwen-plus")
            ),
            openai_max_tokens=_env_int("OPENAI_MAX_TOKENS", 16384),
            openai_temperature=_env_float("OPENAI_TEMPERATURE", 0.5),
            openai_max_retries=_env_int("OPENAI_MAX_RETRIES", _env_int("LLM_HTTP_RETRIES", 3)),
            openai_timeout=_env_float("OPENAI_TIMEOUT", _env_float("LLM_HTTP_TIMEOUT", 20.0)),
            metadata_max_tokens=_env_int("METADATA_MAX_TOKENS", _env_int("OPENAI_MAX_TOKENS", 16384)),
            metadata_temperature=_env_float("METADATA_TEMPERATURE", _env_float("OPENAI_TEMPERATURE", 0.3)),
            extraction_max_tokens=_env_int("EXTRACTION_MAX_TOKENS", _env_int("OPENAI_MAX_TOKENS", 16384)),
            extraction_temperature=_env_float("EXTRACTION_TEMPERATURE", _env_float("OPENAI_TEMPERATURE", 0.5)),
            router_max_tokens=_env_int("ROUTER_MAX_TOKENS", 512),
            router_temperature=_env_float("ROUTER_TEMPERATURE", 0.2),
            summary_max_tokens=_env_int("SUMMARY_MAX_TOKENS", _env_int("OPENAI_MAX_TOKENS", 2048)),
            summary_temperature=_env_float("SUMMARY_TEMPERATURE", 0.7),
        )


@dataclass
class APISettings:
    host: str
    port: int
    debug: bool
    secret_key: str

    @classmethod
    def from_env(cls) -> "APISettings":
        return cls(
            host=_env_str("API_HOST", "0.0.0.0"),
            port=_env_int("API_PORT", 8000),
            debug=_env_bool("API_DEBUG", False),
            secret_key=_env_str("SECRET_KEY", ""),
        )


@dataclass
class DatabaseSettings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_pool_size: int
    postgres_max_overflow: int
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        return cls(
            postgres_host=_env_str("POSTGRES_HOST", "localhost"),
            postgres_port=_env_int("POSTGRES_PORT", 5432),
            postgres_db=_env_str("POSTGRES_DB", "maker"),
            postgres_user=_env_str("POSTGRES_USER", "maker"),
            postgres_password=_env_str("POSTGRES_PASSWORD", ""),
            postgres_pool_size=_env_int("POSTGRES_POOL_SIZE", 20),
            postgres_max_overflow=_env_int("POSTGRES_MAX_OVERFLOW", 0),
            redis_host=_env_str("REDIS_HOST", "localhost"),
            redis_port=_env_int("REDIS_PORT", 6379),
            redis_db=_env_int("REDIS_DB", 0),
            redis_password=_env_str("REDIS_PASSWORD", ""),
        )

    @property
    def postgres_url(self) -> str:
        user = self.postgres_user
        password = self.postgres_password
        auth = f"{user}:{password}@" if password else f"{user}@"
        return (
            f"postgresql+asyncpg://{auth}"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        password = self.redis_password
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@dataclass
class ObjectStorageSettings:
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    minio_bucket: str
    image_base_url: str

    @classmethod
    def from_env(cls) -> "ObjectStorageSettings":
        return cls(
            minio_endpoint=_env_str("MINIO_ENDPOINT", ""),
            minio_access_key=_env_str("MINIO_ACCESS_KEY", ""),
            minio_secret_key=_env_str("MINIO_SECRET_KEY", ""),
            minio_secure=_env_bool("MINIO_SECURE", False),
            minio_bucket=_env_str("MINIO_BUCKET", "maker-documents"),
            image_base_url=_env_str("IMAGE_BASE_URL", ""),
        )


@dataclass
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str
    pool_size: int

    @classmethod
    def from_env(cls) -> "Neo4jSettings":
        return cls(
            uri=_env_str("NEO4J_URI", ""),
            user=_env_str("NEO4J_USER", ""),
            password=_env_str("NEO4J_PASSWORD", ""),
            database=_env_str("NEO4J_DATABASE", "neo4j"),
            pool_size=_env_int("NEO4J_POOL_SIZE", 50),
        )

    @property
    def neo4j_uri(self) -> str:
        return self.uri


    @property
    def neo4j_user(self) -> str:
        return self.user


    @property
    def neo4j_password(self) -> str:
        return self.password


    @property
    def neo4j_database(self) -> str:
        return self.database

    @property
    def neo4j_pool_size(self) -> int:
        return self.pool_size

@dataclass
class Settings:
    app_name: str
    app_version: str
    environment: str
    api: APISettings
    database: DatabaseSettings
    object_storage: ObjectStorageSettings
    llm: LLMSettings
    neo4j: Neo4jSettings
    log_level: str
    log_format: str

    def __init__(self) -> None:
        _load_dotenv()
        self.app_name = _env_str("APP_NAME", "maker")
        self.app_version = _env_str("APP_VERSION", "0.1.0")
        self.environment = _env_str("ENVIRONMENT", "development")
        self.api = APISettings.from_env()
        self.database = DatabaseSettings.from_env()
        self.object_storage = ObjectStorageSettings.from_env()
        self.llm = LLMSettings.from_env()
        self.neo4j = Neo4jSettings.from_env()
        self.graph_storage = self.neo4j
        self.log_level = _env_str("LOG_LEVEL", "INFO")
        self.log_format = _env_str("LOG_FORMAT", "plain")

    @classmethod
    def load_from_yaml(cls, path: str) -> "Settings":
        path_obj = Path(path)
        if not path_obj.exists():
            return cls()
        try:
            import yaml  # type: ignore
        except Exception:
            return cls()
        try:
            data = yaml.safe_load(path_obj.read_text(encoding="utf-8")) or {}
        except Exception:
            return cls()

        app = data.get("app", {}) if isinstance(data, dict) else {}
        _set_env_if_missing("APP_NAME", app.get("name"))
        _set_env_if_missing("APP_VERSION", app.get("version"))
        _set_env_if_missing("ENVIRONMENT", app.get("environment"))
        _set_env_if_missing("LOG_LEVEL", app.get("log_level"))
        _set_env_if_missing("LOG_FORMAT", app.get("log_format"))

        api = data.get("api", {}) if isinstance(data, dict) else {}
        _set_env_if_missing("API_HOST", api.get("host"))
        _set_env_if_missing("API_PORT", api.get("port"))
        _set_env_if_missing("API_DEBUG", api.get("debug"))
        _set_env_if_missing("SECRET_KEY", api.get("secret_key"))

        database = data.get("database", {}) if isinstance(data, dict) else {}
        _set_env_if_missing("POSTGRES_HOST", database.get("postgres_host"))
        _set_env_if_missing("POSTGRES_PORT", database.get("postgres_port"))
        _set_env_if_missing("POSTGRES_DB", database.get("postgres_db"))
        _set_env_if_missing("POSTGRES_USER", database.get("postgres_user"))
        _set_env_if_missing("POSTGRES_PASSWORD", database.get("postgres_password"))
        _set_env_if_missing("POSTGRES_POOL_SIZE", database.get("postgres_pool_size"))
        _set_env_if_missing("POSTGRES_MAX_OVERFLOW", database.get("postgres_max_overflow"))
        _set_env_if_missing("REDIS_HOST", database.get("redis_host"))
        _set_env_if_missing("REDIS_PORT", database.get("redis_port"))
        _set_env_if_missing("REDIS_DB", database.get("redis_db"))
        _set_env_if_missing("REDIS_PASSWORD", database.get("redis_password"))

        object_storage = data.get("object_storage") or data.get("minio") or {}
        if isinstance(object_storage, dict):
            _set_env_if_missing("MINIO_ENDPOINT", object_storage.get("minio_endpoint") or object_storage.get("endpoint"))
            _set_env_if_missing("MINIO_ACCESS_KEY", object_storage.get("minio_access_key") or object_storage.get("access_key"))
            _set_env_if_missing("MINIO_SECRET_KEY", object_storage.get("minio_secret_key") or object_storage.get("secret_key"))
            _set_env_if_missing("MINIO_SECURE", object_storage.get("minio_secure") or object_storage.get("secure"))
            _set_env_if_missing("MINIO_BUCKET", object_storage.get("minio_bucket") or object_storage.get("bucket"))
            _set_env_if_missing("IMAGE_BASE_URL", object_storage.get("image_base_url"))

        return cls()

    @classmethod
    def load_config(cls, path: str) -> "Settings":
        return cls.load_from_yaml(path)

    def to_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment,
            "api": {
                "host": self.api.host,
                "port": self.api.port,
                "debug": self.api.debug,
                "secret_key": self.api.secret_key,
            },
            "database": {
                "postgres_host": self.database.postgres_host,
                "postgres_port": self.database.postgres_port,
                "postgres_db": self.database.postgres_db,
                "postgres_user": self.database.postgres_user,
                "postgres_password": self.database.postgres_password,
                "postgres_pool_size": self.database.postgres_pool_size,
                "postgres_max_overflow": self.database.postgres_max_overflow,
                "redis_host": self.database.redis_host,
                "redis_port": self.database.redis_port,
                "redis_db": self.database.redis_db,
                "redis_password": self.database.redis_password,
            },
            "object_storage": {
                "minio_endpoint": self.object_storage.minio_endpoint,
                "minio_access_key": self.object_storage.minio_access_key,
                "minio_secret_key": self.object_storage.minio_secret_key,
                "minio_secure": self.object_storage.minio_secure,
                "minio_bucket": self.object_storage.minio_bucket,
                "image_base_url": self.object_storage.image_base_url,
            },
            "logging": {"level": self.log_level, "format": self.log_format},
        }

_SETTINGS_CACHE: Optional[Settings] = None


def get_settings() -> Settings:
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is None:
        _SETTINGS_CACHE = Settings()
    return _SETTINGS_CACHE


def reload_settings() -> Settings:
    global _SETTINGS_CACHE
    _SETTINGS_CACHE = Settings()
    return _SETTINGS_CACHE

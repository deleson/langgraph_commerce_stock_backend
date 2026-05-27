from functools import lru_cache

from pydantic import Field,SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="LangGraph Commerce Backend")
    app_version: str = Field(default="0.1.0")
    app_env: str = Field(default="dev")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    app_log_level:str = Field(default="INFO")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/langgraph_commerce"
    )
    database_async_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/langgraph_commerce"
    )
    database_echo:bool = Field(default=False)
    database_pool_pre_ping:bool=Field(default=True)
    database_pool_size:int = Field(default=5)
    database_max_overflow:int = Field(default=10)
    database_pool_timeout_seconds: int = Field(default=30)


    redis_url: str=Field(default="redis://127.0.0.1:6379/0")

    celery_broker_url: str = Field(default="redis://127.0.0.1:6379/1")
    celery_result_backend: str = Field(default="redis://127.0.0.1:6379/2")
    celery_task_default_queue: str = Field(default="default")
    celery_timezone: str = Field(default="Asia/Shanghai")
    celery_enable_utc: bool = Field(default=True)
    celery_task_track_started: bool = Field(default=True)
    celery_task_time_limit_seconds: int = Field(default=1800)
    celery_task_soft_time_limit_seconds: int = Field(default=1500)
    celery_result_expires_seconds: int = Field(default=3600)
    celery_beat_enabled: bool = Field(default=False)
    celery_beat_market_data_sync_enabled: bool = Field(default=False)
    celery_beat_market_data_sync_interval_seconds: int = Field(default=86400)
    celery_beat_market_data_sync_symbol: str = Field(default="AAPL")
    celery_beat_market_data_sync_market: str = Field(default="US")
    celery_beat_market_data_sync_timeframe: str = Field(default="1d")
    celery_beat_market_data_sync_limit: int = Field(default=30)
    celery_beat_market_data_sync_adjust_type: str = Field(default="none")
    celery_beat_market_data_sync_source: str = Field(default="mock")

    jwt_secret_key: str = Field(default="change-this-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)
    jwt_refresh_token_expire_days: int = Field(default=7)
    deepseek_api_key: SecretStr | None = Field(default=None)
    llm_provider: str = Field(default="deepseek")
    llm_model: str = Field(default="deepseek-v4-flash")
    llm_base_url: str = Field(default="https://api.deepseek.com")
    llm_temperature: float = Field(default=0.3)

    http_client_timeout_seconds: float = Field(default=20.0)
    http_client_connect_timeout_seconds: float = Field(default=5.0)

    market_data_enable_real_provider: bool = Field(default=False)
    market_data_primary_provider: str = Field(default="mock")
    market_data_fallback_providers: str = Field(default="mock")
    market_data_default_market: str = Field(default="CN")
    market_data_default_timeframe: str = Field(default="1d")
    market_data_candle_sync_limit: int = Field(default=250)
    market_data_quote_cache_ttl_seconds: int = Field(default=60)
    market_data_request_timeout_seconds: float = Field(default=20.0)
    market_data_cache_enabled: bool = Field(default=True)
    market_data_overview_cache_ttl_seconds: int = Field(default=60)
    market_data_candles_cache_ttl_seconds: int = Field(default=300)
    market_data_quality_cache_ttl_seconds: int = Field(default=300)
    market_data_sync_status_cache_ttl_seconds: int = Field(default=60)
    market_data_technical_indicator_cache_ttl_seconds: int = Field(default=300)

    baostock_enabled: bool = Field(default=True)

    akshare_enabled: bool = Field(default=True)

    tushare_enabled: bool = Field(default=False)
    tushare_token: SecretStr | None = Field(default=None)

    alpha_vantage_enabled: bool = Field(default=False)
    alpha_vantage_api_key: SecretStr | None = Field(default=None)


    api_v1_prefix: str = Field(default="/api/v1")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

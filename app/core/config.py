"""项目配置中心。

该文件通过 pydantic-settings 读取环境变量，并支持用 APP_ENV_FILE
在本地开发、pytest 测试和生产 Docker Compose 环境之间切换配置。

注意：
1. `.env.production` 保存真实密钥和生产连接信息，不能提交 Git。
2. `.env.test` 必须指向测试数据库，避免测试误写生产数据。
3. 业务代码应通过 `get_settings()` 读取配置，避免分散访问环境变量。
"""

from functools import lru_cache

from pydantic import Field,SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from os import getenv

class Settings(BaseSettings):
    """后端运行配置集合。

    Settings 汇总应用基础信息、数据库、Redis、JWT、LLM、行情 Provider、
    Celery 和定时任务等配置，是 API、Service、Repository、Graph、Task
    共同依赖的基础配置对象。
    """

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
    celery_beat_market_symbol_sync_enabled: bool = Field(default=False)
    celery_beat_market_symbol_sync_interval_seconds: int = Field(default=86400)
    celery_beat_market_symbol_sync_market: str = Field(default="CN")
    celery_beat_market_symbol_sync_limit: int | None = Field(default=None)
    celery_beat_market_symbol_sync_provider: str = Field(default="")
    celery_beat_watchlist_candle_sync_enabled: bool = Field(default=False)
    celery_beat_watchlist_candle_sync_hour: int = Field(default=2, ge=0, le=23)
    celery_beat_watchlist_candle_sync_minute: int = Field(default=0, ge=0, le=59)
    celery_beat_watchlist_candle_sync_market: str = Field(default="CN")
    celery_beat_watchlist_candle_sync_timeframe: str = Field(default="1d")
    celery_beat_watchlist_candle_sync_limit: int = Field(default=120, ge=1, le=1000)
    celery_beat_watchlist_candle_sync_adjust_type: str = Field(default="none")
    celery_beat_watchlist_candle_sync_source: str = Field(default="baostock")
    celery_beat_watchlist_candle_sync_fallback_sources: str = Field(default="tushare")
    celery_beat_watchlist_candle_sync_max_symbols: int = Field(default=300, ge=1, le=5000)
    celery_beat_watchlist_candle_sync_batch_size: int = Field(default=50, ge=1, le=500)
    celery_beat_watchlist_candle_sync_stale_after_days: int = Field(default=3, ge=0, le=365)
    celery_beat_watchlist_candle_sync_max_retries: int = Field(default=2, ge=0, le=5)
    celery_beat_daily_report_enabled: bool = Field(default=False)
    celery_beat_daily_report_hour: int = Field(default=18, ge=0, le=23)
    celery_beat_daily_report_minute: int = Field(default=0, ge=0, le=59)
    celery_beat_daily_report_use_ai: bool = Field(default=True)
    celery_beat_daily_report_force_rebuild: bool = Field(default=False)
    celery_beat_daily_report_notify: bool = Field(default=True)
    celery_beat_daily_report_include_candidates: bool = Field(default=True)
    celery_beat_daily_report_include_user_profile: bool = Field(default=True)
    celery_beat_daily_report_include_relevant_memories: bool = Field(default=True)
    celery_beat_daily_report_max_watchlist_items: int = Field(default=20, ge=1, le=100)
    celery_beat_daily_report_max_candidate_items: int = Field(default=5, ge=1, le=20)
    celery_beat_daily_report_batch_size: int = Field(default=200, ge=1, le=1000)
    celery_beat_daily_report_max_retries: int = Field(default=2, ge=0, le=5)

    celery_beat_quant_alert_scan_enabled: bool = Field(default=False)
    celery_beat_quant_alert_scan_interval_seconds: int = Field(default=900, ge=60)
    celery_beat_quant_alert_scan_notify: bool = Field(default=True)
    celery_beat_quant_alert_scan_force: bool = Field(default=False)
    celery_beat_quant_alert_scan_max_watchlist_items: int = Field(default=100, ge=1, le=500)
    celery_beat_quant_alert_scan_batch_size: int = Field(default=200, ge=1, le=1000)
    celery_beat_quant_alert_scan_max_retries: int = Field(default=2, ge=0, le=5)

    celery_beat_paper_trading_tick_enabled: bool = Field(default=False)
    celery_beat_paper_trading_tick_hour: int = Field(default=20, ge=0, le=23)
    celery_beat_paper_trading_tick_minute: int = Field(default=30, ge=0, le=59)
    celery_beat_paper_trading_tick_notify: bool = Field(default=False)
    celery_beat_paper_trading_tick_force: bool = Field(default=False)
    celery_beat_paper_trading_tick_max_symbols: int = Field(default=50, ge=1, le=500)
    celery_beat_paper_trading_tick_batch_size: int = Field(default=200, ge=1, le=1000)
    celery_beat_paper_trading_tick_max_retries: int = Field(default=2, ge=0, le=5)

    jwt_secret_key: str = Field(default="change-this-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)
    jwt_refresh_token_expire_days: int = Field(default=7)
    auth_single_session_per_device_category_enabled: bool = Field(default=True)
    auth_single_session_unknown_category_enabled: bool = Field(default=False)
    auth_access_token_session_check_enabled: bool = Field(default=True)
    auth_blacklist_replaced_access_token: bool = Field(default=True)
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
    market_symbol_primary_provider: str = Field(default="tushare")
    market_symbol_fallback_providers: str = Field(default="baostock,mock")
    market_symbol_sync_provider: str = Field(default="")
    market_symbol_exact_lookup_provider: str = Field(default="baostock")

    baostock_enabled: bool = Field(default=True)

    akshare_enabled: bool = Field(default=True)

    tushare_enabled: bool = Field(default=False)
    tushare_token: SecretStr | None = Field(default=None)

    alpha_vantage_enabled: bool = Field(default=False)
    alpha_vantage_api_key: SecretStr | None = Field(default=None)


    api_v1_prefix: str = Field(default="/api/v1")

    model_config = SettingsConfigDict(
        # APP_ENV_FILE 让同一套代码可以在开发、测试、生产环境读取不同 env 文件。
        env_file=getenv("APP_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """返回全局配置实例。

    使用 lru_cache 避免每次请求都重新解析环境变量。
    如果测试或脚本需要切换 APP_ENV_FILE，应在新进程中执行或显式清理缓存。
    """

    return Settings()

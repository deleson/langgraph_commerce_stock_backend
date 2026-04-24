from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="LangGraph Commerce Backend")
    app_version: str = Field(default="0.1.0")
    app_env: str = Field(default="dev")
    app_debug: bool = Field(default=True)
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    app_log_level:str = Field(default="INFO")
    database_url:str = Field(
        default="postgresql+psycopg://postgres:postgres@127.0.0.1:5432/langgraph_commerce"
    )
    database_echo:bool = Field(default=False)
    database_pool_pre_ping:bool=Field(default=True)
    database_pool_size:int = Field(default=0)
    database_max_overflow:int = Field(default=20)

    redis_url: str=Field(default="redis://127.0.0.1:6379/0")

    jwt_secret_key: str = Field(default="change-this-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)


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

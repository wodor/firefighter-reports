from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str = Field(
        ...,
        alias="LLM_API_KEY",
    )
    llm_model: str = Field(
        "gpt-4o-mini",
        alias="LLM_MODEL",
    )
    llm_provider: str | None = Field(None, alias="LLM_PROVIDER")
    slack_bot_token: str = Field(..., alias="SLACK_BOT_TOKEN")
    slack_user_token: str = Field(..., alias="SLACK_USER_TOKEN")
    slack_channel_id: str = Field(..., alias="SLACK_CHANNEL_ID")
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    search_query: str = Field("@platform-firefighter", alias="SEARCH_QUERY")
    search_limit: int = Field(50, alias="SEARCH_LIMIT")
    lookback_days: int = Field(7, alias="LOOKBACK_DAYS")
    user_cache_ttl: int = Field(7200, alias="USER_CACHE_TTL")
    thread_cache_ttl: int = Field(3600, alias="THREAD_CACHE_TTL")
    max_threads: int = Field(10, alias="MAX_THREADS")
    dry_run: bool = Field(False, alias="DRY_RUN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


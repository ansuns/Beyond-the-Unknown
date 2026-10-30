from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_JWT_SECRET = "local-development-jwt-secret-change-before-deploy"
_LOCAL_OPENID_SECRET = "local-development-openid-hmac-change-before-deploy"


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "Beyond the Unknown API"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://beyond:beyond_dev_only@localhost:5432/beyond"
    rabbitmq_url: str = "amqp://beyond:beyond_dev_only@localhost:5672/"
    rabbitmq_task_queue: str = "game.tasks.v1"
    rabbitmq_retry_delay_ms: int = Field(default=5_000, ge=100, le=60_000)
    rabbitmq_max_retries: int = Field(default=3, ge=0, le=19)
    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None
    wechat_api_url: str = "https://api.weixin.qq.com/sns/jscode2session"
    wechat_api_timeout_seconds: float = 5.0
    jwt_secret: str = _LOCAL_JWT_SECRET
    jwt_access_token_seconds: int = 3600
    openid_hmac_secret: str = _LOCAL_OPENID_SECRET
    map_instance_max_players: int = 20
    map_reconnect_grace_seconds: int = 60
    map_max_speed: float = 160.0
    map_move_rate_hz: float = 10.0
    map_action_rate_limit: int = 5
    map_action_window_seconds: int = 10
    server_timezone: str = "UTC"
    season_review_window_seconds: int = Field(default=600, ge=300, le=600)
    internal_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def validate_auth_secrets(self) -> None:
        if len(self.jwt_secret) < 32 or len(self.openid_hmac_secret) < 32:
            raise ValueError(
                "JWT_SECRET and OPENID_HMAC_SECRET must contain at least 32 characters"
            )
        if self.app_env not in {"local", "test"}:
            if (
                self.jwt_secret == _LOCAL_JWT_SECRET
                or self.openid_hmac_secret == _LOCAL_OPENID_SECRET
            ):
                raise ValueError(
                    "Production authentication secrets must be explicitly configured"
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()

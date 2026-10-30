from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_name: str = "Beyond the Unknown API"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://beyond:beyond_dev_only@localhost:5432/beyond"
    rabbitmq_url: str = "amqp://beyond:beyond_dev_only@localhost:5672/"
    rabbitmq_task_queue: str = "game.tasks.v1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

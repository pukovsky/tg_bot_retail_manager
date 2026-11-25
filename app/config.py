from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    postgres_port: int = 5432
    database_url: SecretStr

    # Telegram & LLM
    telegram_bot_token: SecretStr
    openai_api_key: SecretStr

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
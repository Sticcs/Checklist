from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Must be a fixed value (set via .env), not regenerated per boot - otherwise
    # every server restart invalidates every logged-in session's cookie.
    secret_key: str = "dev-secret-change-me"
    db_path: str = str(Path(__file__).resolve().parent.parent.parent / "checklist.db")
    cookie_name: str = "session"
    cookie_max_age: int = 60 * 60 * 24 * 30  # 30 days


settings = Settings()

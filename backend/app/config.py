from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Must be a fixed value (set via .env / a Fly secret in production), not
    # regenerated per boot - otherwise every server restart invalidates every
    # logged-in session's cookie.
    secret_key: str = "dev-secret-change-me"
    db_path: str = str(Path(__file__).resolve().parent.parent.parent / "checklist.db")
    # Postgres connection string for production (Render + Neon/Supabase). When
    # unset, db.py falls back to the sqlite db_path above - local dev needs no
    # setup and keeps using the plain checklist.db file.
    database_url: str | None = None
    cookie_name: str = "session"
    cookie_max_age: int = 60 * 60 * 24 * 30  # 30 days
    # Cookies must be Secure over HTTPS in production (Fly.io terminates TLS
    # for us) - but a Secure cookie is silently dropped by the browser over
    # plain http, which local dev uses, so this needs to be togglable rather
    # than hardcoded either way.
    cookie_secure: bool = False


settings = Settings()

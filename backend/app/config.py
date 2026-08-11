from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import user_data_dir


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Must be a fixed value (set via .env / a Fly secret in production), not
    # regenerated per boot - otherwise every server restart invalidates every
    # logged-in session's cookie.
    secret_key: str = "dev-secret-change-me"
    db_path: str = str(user_data_dir() / "checklist.db")
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
    # Google OAuth ("Sign in with Google" - app/routers/auth.py). Unset means
    # the feature is simply unavailable (the login route 503s) rather than
    # erroring at startup - local dev and the desktop app's own local server
    # never need these, only the deployed site does.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Where Google should redirect back to, and what the desktop app points
    # its "Sign in with Google" link straight at (see useIsDesktopApp on the
    # frontend) - deliberately the one account path that requires internet
    # and always talks to the *real* deployed backend, even from inside the
    # otherwise fully-offline desktop app, since that's what makes "same
    # Google account -> same tasks on both" true.
    public_base_url: str = "https://checklist-kmtw.onrender.com"


settings = Settings()

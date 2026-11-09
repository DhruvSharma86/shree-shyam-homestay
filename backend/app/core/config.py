"""Environment-based application settings.

All configuration comes from environment variables (or a gitignored ``.env``
file). Nothing secret is ever hardcoded. See ``.env.example`` for the full
list of supported variables.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_name: str = "Shree Shyam Home Stay Management System"
    app_env: str = "development"  # development | staging | production
    app_debug: bool = False
    log_level: str = "INFO"

    # --- Database --------------------------------------------------------
    # PostgreSQL is the production database. SQLAlchemy URL, e.g.:
    #   postgresql+psycopg://user:password@localhost:5432/shree_shyam
    # The default points at the docker-compose ``db`` service. SQLite is
    # supported only as a local/test convenience (see db.py).
    database_url: str = "postgresql+psycopg://hotel_app:change_me@localhost:5432/shree_shyam"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30

    # --- API -------------------------------------------------------------
    api_v1_prefix: str = "/api/v1"
    # Comma-separated browser origins allowed to call the API with
    # credentials. Default keeps local frontend dev working. Production
    # must set the real frontend origin (wildcard is rejected in production).
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS origins (trimmed, non-empty entries only)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- Secrets (required in production; placeholders are for local dev) -
    # Session signing / encryption keys are introduced in Phase 1.2 with the
    # authentication system. They are declared here so the shape is stable.
    session_secret: str = "dev-only-insecure-secret-change-me"
    session_cookie_name: str = "sshs_session"
    csrf_cookie_name: str = "sshs_csrf"
    session_idle_timeout_minutes: int = 30
    session_absolute_timeout_hours: int = 12

    # --- Login rate limiting ------------------------------------------------
    # Per-username failed-login budget inside a sliding window.
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 300

    # --- Guest portal rate limiting (Priority 3 audit) ----------------------
    # Per-IP failed-portal-access budget. A per-token key is useless here:
    # every guessed token is a fresh key, so the limiter must be keyed by
    # client IP (shared NAT users share the budget — intentional DoS brake).
    portal_rate_limit_attempts: int = 60
    portal_rate_limit_window_seconds: int = 300

    # --- Trusted proxy -------------------------------------------------------
    # When True, `X-Forwarded-For` is honoured for client-IP resolution
    # (rate-limit keys + audit IPs). Only enable behind a reverse proxy that
    # strips/spoof-proofs XFF; otherwise IPs are client-controlled. Default
    # False = use the direct peer only.
    trusted_proxy_enabled: bool = False

    # --- Initial admin bootstrap (Phase 1.2) -----------------------------
    # Used only to create the first ADMIN account when the users table is
    # empty. Empty = no bootstrap. Never commit real values.
    initial_admin_username: str = ""
    initial_admin_password: str = ""
    initial_admin_full_name: str = "Hotel Administrator"

    @property
    def is_production(self) -> bool:
        """Return True when running in the production environment."""
        return self.app_env.lower() == "production"

    @model_validator(mode="after")
    def _guard_production_settings(self) -> "Settings":
        """Fail fast on unsafe production configuration (never silently dev)."""
        if not self.is_production:
            return self
        if self.app_debug:
            raise ValueError("APP_DEBUG must be False in production.")
        if self.session_secret == "dev-only-insecure-secret-change-me":
            raise ValueError("SESSION_SECRET must be set to a strong value in production.")
        if self.database_url.startswith("sqlite"):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL (not SQLite).")
        if "change_me" in self.database_url:
            raise ValueError("Production DATABASE_URL must not contain the placeholder password.")
        origins = self.cors_origin_list
        if not origins:
            raise ValueError("CORS_ORIGINS must list the frontend origin in production.")
        if "*" in origins:
            raise ValueError("Wildcard CORS origins are forbidden in production (credentials).")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()

"""Tests for environment-based configuration."""

from app.core.config import Settings, get_settings


def test_settings_defaults() -> None:
    """Settings expose safe local-development defaults."""
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.session_idle_timeout_minutes == 30


def test_settings_from_environment(monkeypatch) -> None:
    """Environment variables override defaults (config never reads code)."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    settings = Settings()
    assert settings.app_env == "production"
    assert settings.is_production is True
    assert settings.log_level == "WARNING"


def test_get_settings_is_cached() -> None:
    """get_settings returns the same cached instance."""
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    get_settings.cache_clear()
